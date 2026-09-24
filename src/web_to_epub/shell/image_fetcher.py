"""Fetch an image over HTTP(S), validating every hop against the core policy.

DNS is resolved once per hop, the resolved addresses are validated, and the
connection is made to the validated IP (no second lookup, so no DNS rebinding).
The Host header and TLS SNI/verification use the original hostname.
"""

import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.core.image_policy import (
    DEFAULT_MAX_BYTES,
    check_address,
    check_response,
    check_url,
    media_type,
)

_REDIRECT_CODES = (301, 302, 303, 307, 308)
_CHUNK = 65536


@dataclass(frozen=True)
class FetchWarning:
    url: str
    reason: str


@dataclass(frozen=True)
class FetchResult:
    image: ImageData | None = None
    warning: FetchWarning | None = None


class _Refused(Exception):
    pass


class _PinnedConnection(http.client.HTTPConnection):
    """HTTP(S) connection to an already-validated IP, TLS verified against hostname."""

    def __init__(self, ip, port, hostname, timeout, tls_context):
        super().__init__(ip, port, timeout=timeout)
        self._hostname = hostname
        self._tls_context = tls_context

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self._tls_context is not None:
            sock = self._tls_context.wrap_socket(sock, server_hostname=self._hostname)
        self.sock = sock


def _validated_addresses(host: str, port: int, allow_loopback: bool) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [info[4][0] for info in infos]
    for address in addresses:
        verdict = check_address(address, allow_loopback)
        if not verdict.allowed:
            raise _Refused(verdict.reason)
    return addresses


def _connect(parsed, allow_loopback, timeout, tls_context):
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    last_error: Exception = _Refused("no addresses")
    for address in _validated_addresses(host, port, allow_loopback):
        conn = _PinnedConnection(address, port, host, timeout, tls_context)
        try:
            conn.connect()
            return conn
        except OSError as exc:
            conn.close()
            last_error = exc
    raise last_error


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise _Refused("timed out (total time limit exceeded)")


def _read_limited(response, max_bytes: int, deadline: float) -> bytes:
    chunks = []
    total = 0
    # read1 returns after one socket read, so the deadline is checked even on a slow drip
    while chunk := response.read1(_CHUNK):
        _check_deadline(deadline)
        total += len(chunk)
        if total > max_bytes:
            raise _Refused(f"response too large: > {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch(url, allow_loopback, max_bytes, timeout, max_redirects, ca_file, deadline) -> ImageData:
    current = url
    tls_context = None
    for _ in range(max_redirects + 1):
        _check_deadline(deadline)
        verdict = check_url(current, allow_loopback)
        if not verdict.allowed:
            raise _Refused(verdict.reason)
        parsed = urlparse(current)
        if parsed.scheme == "https" and tls_context is None:
            tls_context = ssl.create_default_context(cafile=ca_file)
        conn = _connect(
            parsed, allow_loopback, timeout, tls_context if parsed.scheme == "https" else None
        )
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            conn.request("GET", target, headers={"Host": parsed.netloc, "Accept": "image/*"})
            response = conn.getresponse()
            if response.status in _REDIRECT_CODES:
                location = response.getheader("Location")
                if not location:
                    raise _Refused("redirect without Location")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise _Refused(f"HTTP status {response.status}")
            content_type = response.getheader("Content-Type")
            size = int(response.getheader("Content-Length") or 0)
            verdict = check_response(content_type, size, max_bytes)
            if not verdict.allowed:
                raise _Refused(verdict.reason)
            data = _read_limited(response, max_bytes, deadline)
            return ImageData(data=data, media_type=media_type(content_type))
        finally:
            conn.close()
    raise _Refused("too many redirects")


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
    deadline = time.monotonic() + deadline_seconds
    try:
        image = _fetch(
            url, allow_loopback_for_tests, max_bytes, timeout, max_redirects, ca_file, deadline
        )
    except Exception as exc:  # never raise to the caller
        return FetchResult(warning=FetchWarning(url=url, reason=str(exc) or type(exc).__name__))
    return FetchResult(image=image)
