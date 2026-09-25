"""Fetch an image over HTTP(S), validating every hop against the core policy.

The validated, DNS-pinned, redirect-checked transport lives in `safe_http`.
"""

from dataclasses import dataclass

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.core.image_policy import (
    DEFAULT_MAX_BYTES,
    check_response,
    media_type,
)
from web_to_epub.shell.safe_http import safe_get


@dataclass(frozen=True)
class FetchWarning:
    url: str
    reason: str


@dataclass(frozen=True)
class FetchResult:
    image: ImageData | None = None
    warning: FetchWarning | None = None


def fetch_image(
    url: str,
    *,
    allow_loopback_for_tests: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 10.0,
    max_redirects: int = 5,
    ca_file: str | None = None,
    deadline_seconds: float = 30.0,
) -> FetchResult:
    """`timeout` bounds each socket operation; `deadline_seconds` bounds the whole fetch."""
    try:
        response = safe_get(
            url,
            accept="image/*",
            validate_response=check_response,
            allow_loopback=allow_loopback_for_tests,
            max_bytes=max_bytes,
            timeout=timeout,
            max_redirects=max_redirects,
            ca_file=ca_file,
            deadline_seconds=deadline_seconds,
        )
        image = ImageData(data=response.data, media_type=media_type(response.content_type))
    except Exception as exc:  # never raise to the caller
        return FetchResult(warning=FetchWarning(url=url, reason=str(exc) or type(exc).__name__))
    return FetchResult(image=image)
