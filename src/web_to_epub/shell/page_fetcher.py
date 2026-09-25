"""Fetch an HTML page over HTTP(S) via the validated `safe_http` transport."""

from dataclasses import dataclass

from web_to_epub.core.image_policy import DEFAULT_MAX_BYTES, check_page_response
from web_to_epub.shell.image_fetcher import FetchWarning
from web_to_epub.shell.safe_http import safe_get

_USER_AGENT = "web-to-epub/0.1"
_ACCEPT = "text/html,application/xhtml+xml;q=0.9"


@dataclass(frozen=True)
class FetchedPage:
    data: bytes
    content_type: str
    final_url: str


@dataclass(frozen=True)
class PageResult:
    page: FetchedPage | None = None
    warning: FetchWarning | None = None


def fetch_page(
    url: str,
    *,
    allow_loopback_for_tests: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 10.0,
    max_redirects: int = 5,
    ca_file: str | None = None,
    deadline_seconds: float = 30.0,
) -> PageResult:
    try:
        response = safe_get(
            url,
            accept=_ACCEPT,
            validate_response=check_page_response,
            allow_loopback=allow_loopback_for_tests,
            max_bytes=max_bytes,
            timeout=timeout,
            max_redirects=max_redirects,
            ca_file=ca_file,
            deadline_seconds=deadline_seconds,
            extra_headers={"User-Agent": _USER_AGENT},
        )
        page = FetchedPage(
            data=response.data,
            content_type=response.content_type or "",
            final_url=response.final_url,
        )
    except Exception as exc:  # never raise to the caller
        return PageResult(warning=FetchWarning(url=url, reason=str(exc) or type(exc).__name__))
    return PageResult(page=page)
