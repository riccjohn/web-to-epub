"""Pure image fetch policy: URL, resolved-address and response checks."""

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
# Formats every EPUB reader handles. SVG is excluded on purpose: it can carry script.
IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
PAGE_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}


def matches_signature(data: bytes, kind: str) -> bool:
    """True if `data` starts with the magic bytes of the image type `kind`."""
    if kind == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if kind == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if kind == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str


def _allow() -> Verdict:
    return Verdict(allowed=True, reason="")


def _deny(reason: str) -> Verdict:
    return Verdict(allowed=False, reason=reason)


def media_type(content_type: str | None) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def check_address(address: str, allow_loopback: bool = False) -> Verdict:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return _deny(f"unparseable address: {address!r}")
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global and not (allow_loopback and ip.is_loopback):
        return _deny(f"non-public address: {ip}")
    return _allow()


def check_url(url: str, allow_loopback: bool = False) -> Verdict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _deny(f"unsupported scheme: {parsed.scheme!r}")
    if parsed.username is not None or parsed.password is not None:
        return _deny("URL contains credentials")
    host = parsed.hostname
    if not host:
        return _deny("URL has no host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return _allow()  # hostname; resolved addresses are checked separately
    return check_address(host, allow_loopback)


def check_response(
    content_type: str | None, size: int, max_bytes: int = DEFAULT_MAX_BYTES
) -> Verdict:
    if media_type(content_type) not in IMAGE_EXTENSIONS:
        return _deny(f"unsupported image content type: {content_type!r}")
    if size > max_bytes:
        return _deny(f"response too large: {size} > {max_bytes}")
    return _allow()


def check_page_response(
    content_type: str | None, size: int, max_bytes: int = DEFAULT_MAX_BYTES
) -> Verdict:
    if media_type(content_type) not in PAGE_MEDIA_TYPES:
        return _deny(f"unsupported page content type: {content_type!r}")
    if size > max_bytes:
        return _deny(f"response too large: {size} > {max_bytes}")
    return _allow()
