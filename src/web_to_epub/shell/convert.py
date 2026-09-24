"""Convert use case: uploaded markdown/text files in, EPUB bytes out."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import PurePath

from web_to_epub.core.epub_builder import BookMetadata, ImageData, build_epub
from web_to_epub.core.markdown_chapter import parse_chapter
from web_to_epub.core.ordering import natural_sort
from web_to_epub.shell.image_fetcher import FetchWarning, fetch_image

# Keep in sync with EXT in static/app.js
_EXTENSIONS = {".md", ".markdown", ".txt"}
_FETCH_WORKERS = 5


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
    for name, _ in files:
        if PurePath(name).suffix.lower() not in _EXTENSIONS:
            return ConvertError("unsupported_type", f"Unsupported file type: {name}", name)
    if sum(len(data) for _, data in files) > options.max_total_bytes:
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
    chapters = [parse_chapter(contents[n], n, options.strip_suffix) for n in ordered]

    urls = list(dict.fromkeys(
        ref.src for chapter in chapters for ref in chapter.images if ref.is_remote
    ))

    def fetch(url: str):
        return fetch_image(url, allow_loopback_for_tests=options.allow_loopback_for_tests)

    images: dict[str, ImageData] = {}
    warnings: list[FetchWarning] = []
    if urls:
        # pool.map keeps input order, so warnings and images stay deterministic
        with ThreadPoolExecutor(max_workers=min(_FETCH_WORKERS, len(urls))) as pool:
            for url, fetched in zip(urls, pool.map(fetch, urls)):
                if fetched.image is not None:
                    images[url] = fetched.image
                elif fetched.warning not in warnings:
                    warnings.append(fetched.warning)

    metadata = BookMetadata(options.title, options.author, options.language, options.description)
    return Result(build_epub(chapters, metadata, images, options.cover), warnings)
