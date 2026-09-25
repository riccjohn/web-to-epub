"""Fetch a list of page URLs and turn them into reviewable markdown chapters."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from web_to_epub.core.charset import decode_html
from web_to_epub.core.page_markdown import page_to_markdown
from web_to_epub.core.url_list import chapter_filename, normalize_url
from web_to_epub.shell.page_fetcher import PageResult, fetch_page


@dataclass(frozen=True)
class PageChapter:
    filename: str
    url: str
    title: str
    markdown: str


@dataclass(frozen=True)
class PageFailure:
    url: str
    message: str


def fetch_pages(
    urls: list[str],
    *,
    allow_loopback_for_tests: bool = False,
    max_urls: int = 50,
    budget_seconds: float = 120.0,
    max_workers: int = 4,
    timeout: float = 10.0,
) -> list[PageChapter | PageFailure]:
    if len(urls) > max_urls:
        raise ValueError(f"too many URLs: {len(urls)} (max {max_urls})")

    fetched: list[PageResult | None] = [None] * len(urls)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for start in range(0, len(urls), max_workers):
            remaining = budget_seconds - (time.monotonic() - started)
            if remaining <= 0:
                break

            def fetch(url: str, deadline: float = remaining) -> PageResult:
                return fetch_page(
                    url,
                    allow_loopback_for_tests=allow_loopback_for_tests,
                    timeout=timeout,
                    deadline_seconds=deadline,
                )

            batch = urls[start : start + max_workers]
            fetched[start : start + len(batch)] = pool.map(fetch, batch)

    filenames = [chapter_filename(i, url) for i, url in enumerate(urls)]
    chapter_files: dict[str, str] = {}
    for url, filename, result in zip(urls, filenames, fetched):
        if result is not None and result.page is not None:
            chapter_files[normalize_url(url)] = filename
            chapter_files[normalize_url(result.page.final_url)] = filename

    results: list[PageChapter | PageFailure] = []
    for url, filename, result in zip(urls, filenames, fetched):
        if result is None:
            results.append(PageFailure(url, "skipped: fetch budget exhausted"))
        elif result.page is None:
            results.append(PageFailure(url, result.warning.reason))
        else:
            results.append(_to_chapter(url, filename, result, chapter_files))
    return results


def _to_chapter(url, filename, result, chapter_files) -> PageChapter | PageFailure:
    page = result.page
    try:
        html = decode_html(page.data, page.content_type)
        converted = page_to_markdown(html, page.final_url, chapter_files)
    except Exception as exc:
        return PageFailure(url, f"could not convert page: {exc}")
    if not converted.markdown.removeprefix(f"# {converted.title}").strip():
        return PageFailure(url, "no readable content")
    return PageChapter(filename, url, converted.title, converted.markdown)
