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

    started = time.monotonic()

    def fetch(url: str) -> PageResult | None:
        remaining = budget_seconds - (time.monotonic() - started)
        if remaining <= 0:
            return None
        return fetch_page(
            url,
            allow_loopback_for_tests=allow_loopback_for_tests,
            timeout=timeout,
            deadline_seconds=remaining,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fetched = list(pool.map(fetch, urls))

    filenames = [chapter_filename(i, url) for i, url in enumerate(urls)]

    # Pass 1: convert without link rewriting to learn which pages become chapters.
    # Only those may be link targets; a link to a page that fails stays a working URL.
    converted = [
        _to_chapter(url, filename, result, None)
        if result is not None and result.page is not None
        else None
        for url, filename, result in zip(urls, filenames, fetched)
    ]
    ok = [isinstance(c, PageChapter) for c in converted]

    # Pages that end up at the same final URL (a redirect to another listed page, or two
    # URLs redirecting to one) are one chapter. Prefer the page requested at that URL.
    owner: dict[str, int] = {}
    for i, url in enumerate(urls):
        if ok[i] and _key(fetched[i].page.final_url) == _key(url):
            owner.setdefault(_key(url), i)
    for i in range(len(urls)):
        if ok[i]:
            owner.setdefault(_key(fetched[i].page.final_url), i)

    duplicate_of: dict[int, int] = {}
    chapter_files: dict[str, str] = {}
    for i, url in enumerate(urls):
        if not ok[i]:
            continue
        final_owner = owner[_key(fetched[i].page.final_url)]
        if final_owner != i:
            duplicate_of[i] = final_owner
        chapter_files[_key(url)] = filenames[final_owner]
        chapter_files[_key(fetched[i].page.final_url)] = filenames[final_owner]

    # Pass 2: convert the surviving chapters with links rewritten.
    results: list[PageChapter | PageFailure] = []
    for i, (url, filename, result) in enumerate(zip(urls, filenames, fetched)):
        if result is None:
            results.append(PageFailure(url, "skipped: fetch budget exhausted"))
        elif result.page is None:
            results.append(PageFailure(url, result.warning.reason))
        elif not ok[i]:
            results.append(converted[i])
        elif i in duplicate_of:
            results.append(PageFailure(url, f"duplicate of {urls[duplicate_of[i]]}"))
        else:
            results.append(_to_chapter(url, filename, result, chapter_files))
    return results


def _key(url: str) -> str:
    try:
        return normalize_url(url)
    except ValueError:
        return url


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
