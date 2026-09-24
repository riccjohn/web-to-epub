"""Convert use case: uploaded markdown/text files in, EPUB bytes out."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePath

from web_to_epub.core.data_uri import decode_data_uri
from web_to_epub.core.epub_builder import BookMetadata, ImageData, build_epub
from web_to_epub.core.image_policy import DEFAULT_MAX_BYTES, IMAGE_EXTENSIONS
from web_to_epub.core.markdown_chapter import parse_chapter
from web_to_epub.core.ordering import natural_sort
from web_to_epub.shell.image_fetcher import FetchWarning, fetch_image

# Keep in sync with EXT in static/app.js
_EXTENSIONS = {".md", ".markdown", ".txt"}
_FETCH_WORKERS = 5
_WARNING_URL_MAX = 80


@dataclass(frozen=True)
class Options:
    title: str = ""
    author: str = ""
    language: str = "en"
    description: str = ""
    strip_suffix: str | None = None
    order: list[str] | None = None
    cover: ImageData | None = None
    max_total_bytes: int = 50 * 1024 * 1024
    max_image_total_bytes: int = 100 * 1024 * 1024
    fetch_budget_seconds: float = 120.0
    allow_loopback_for_tests: bool = False


@dataclass(frozen=True)
class Result:
    epub_bytes: bytes
    warnings: list[FetchWarning] = field(default_factory=list)


@dataclass(frozen=True)
class ConvertError:
    code: str
    message: str
    filename: str | None = None


def convert(files: list[tuple[str, bytes]], options: Options) -> Result | ConvertError:
    if not options.title.strip():
        return ConvertError("missing_title", "A title is required")
    if not options.author.strip():
        return ConvertError("missing_author", "An author is required")
    if not files:
        return ConvertError("no_files", "No files were provided")
    seen_names: set[str] = set()
    for name, _ in files:
        if PurePath(name).suffix.lower() not in _EXTENSIONS:
            return ConvertError("unsupported_type", f"Unsupported file type: {name}", name)
        if name in seen_names:
            return ConvertError("duplicate_filename", f"Duplicate file name: {name}", name)
        seen_names.add(name)
    if options.cover is not None and (
        options.cover.media_type not in IMAGE_EXTENSIONS or not options.cover.data
    ):
        return ConvertError("bad_cover", "The cover must be a PNG, JPEG, GIF or WebP image")
    cover_size = len(options.cover.data) if options.cover is not None else 0
    if sum(len(data) for _, data in files) + cover_size > options.max_total_bytes:
        return ConvertError("too_large", "Total upload size is too large")

    contents: dict[str, str] = {}
    for name, data in files:
        try:
            contents[name] = data.decode("utf-8")
        except UnicodeDecodeError:
            return ConvertError("not_utf8", f"File is not valid UTF-8: {name}", name)

    if options.order is not None:
        seen: set[str] = set()
        for name in options.order:
            if name not in contents or name in seen:
                return ConvertError("bad_order", f"Invalid order entry: {name}", name)
            seen.add(name)
        for name in contents:
            if name not in seen:
                return ConvertError("bad_order", f"File missing from order: {name}", name)
    ordered = options.order if options.order is not None else natural_sort(list(contents))
    chapters = []
    for name in ordered:
        chapter = parse_chapter(contents[name], name, options.strip_suffix)
        if not chapter.body.strip():
            return ConvertError("empty_file", f"File has no content: {name}", name)
        chapters.append(chapter)

    sources: dict[str, bool] = {}  # src -> is_remote, in document order
    for chapter in chapters:
        for ref in chapter.images:
            if ref.src:
                sources.setdefault(ref.src, ref.is_remote)
    images, warnings = _collect_images(list(sources.items()), options)

    metadata = BookMetadata(options.title, options.author, options.language, options.description)
    return Result(build_epub(chapters, metadata, images, options.cover), warnings)


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used


def _shown(url: str) -> str:
    return url if len(url) <= _WARNING_URL_MAX else url[:_WARNING_URL_MAX] + "…"


def _collect_images(
    sources: list[tuple[str, bool]], options: Options
) -> tuple[dict[str, ImageData], list[FetchWarning]]:
    """Resolve images in document order against one shared byte budget.

    Consecutive remote URLs are fetched in small parallel batches so the byte and time budgets
    stop the work, not just the results. data: URIs are decoded inline; other local sources
    (relative paths) cannot be resolved, so they only warn.
    """
    images: dict[str, ImageData] = {}
    warnings: list[FetchWarning] = []
    budget = _Budget(options.max_image_total_bytes)
    started = time.monotonic()
    pending: list[str] = []

    def warn(url: str, reason: str) -> None:
        warning = FetchWarning(_shown(url), reason)
        if warning not in warnings:
            warnings.append(warning)

    def flush(pool: ThreadPoolExecutor) -> None:
        batch = pending[:]
        pending.clear()
        if not batch:
            return
        remaining = options.fetch_budget_seconds - (time.monotonic() - started)
        if remaining <= 0 or budget.remaining <= 0:
            for url in batch:
                warn(url, "skipped: image fetch budget exhausted")
            return

        def fetch(url: str):
            return fetch_image(
                url,
                allow_loopback_for_tests=options.allow_loopback_for_tests,
                deadline_seconds=remaining,
            )

        # pool.map keeps input order, so warnings and images stay deterministic
        for url, fetched in zip(batch, pool.map(fetch, batch)):
            if fetched.image is None:
                warn(fetched.warning.url, fetched.warning.reason)
            elif len(fetched.image.data) > budget.remaining:
                warn(url, "skipped: image size budget exceeded")
            else:
                budget.used += len(fetched.image.data)
                images[url] = fetched.image

    def embed(src: str) -> None:
        if not src.lower().startswith("data:"):
            warn(src, "only http(s) and data: image sources are supported")
        elif budget.remaining <= 0:
            warn(src, "skipped: image size budget exceeded")
        else:
            cap = min(DEFAULT_MAX_BYTES, budget.remaining)
            try:
                image = decode_data_uri(src, cap)
            except ValueError as exc:
                over_budget = cap < DEFAULT_MAX_BYTES and "too large" in str(exc)
                warn(src, "skipped: image size budget exceeded" if over_budget else str(exc))
                return
            budget.used += len(image.data)
            images[src] = image

    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
        for src, is_remote in sources:
            if is_remote:
                pending.append(src)
                if len(pending) == _FETCH_WORKERS:
                    flush(pool)
            else:
                flush(pool)
                embed(src)
        flush(pool)
    return images, warnings
