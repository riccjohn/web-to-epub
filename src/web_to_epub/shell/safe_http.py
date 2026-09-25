"""Validated, DNS-pinned, redirect-checked HTTP(S) GET shared by fetchers.

DNS is resolved once per hop, the resolved addresses are validated, and the
connection is made to the validated IP (no second lookup, so no DNS rebinding).
The Host header and TLS SNI/verification use the original hostname.
"""

import http.client
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from web_to_epub.core.image_policy import Verdict, check_address, check_url

_REDIRECT_CODES = (301, 302, 303, 307, 308)
_CHUNK = 65536

# (content_type, declared_size, max_bytes) -> Verdict
ResponseValidator = Callable[[str | None, int, int], Verdict]


class Refused(Exception):
    pass


@dataclass(frozen=True)
class SafeResponse:
    data: bytes
    content_type: str | None
    final_url: str


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
            raise Refused(verdict.reason)
    return addresses


def _connect(parsed, allow_loopback, timeout, tls_context):
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    last_error: Exception = Refused("no addresses")
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
        raise Refused("timed out (total time limit exceeded)")


def _read_limited(response, max_bytes: int, deadline: float) -> bytes:
    chunks = []
    total = 0
    # read1 returns after one socket read, so the deadline is checked even on a slow drip
    while chunk := response.read1(_CHUNK):
        _check_deadline(deadline)
        total += len(chunk)
        if total > max_bytes:
            raise Refused(f"response too large: > {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch(
    url,
    accept,
    validate_response,
    allow_loopback,
    max_bytes,
    timeout,
    max_redirects,
    ca_file,
    deadline,
    extra_headers,
) -> SafeResponse:
    current = url
    tls_context = None
    for _ in range(max_redirects + 1):
        _check_deadline(deadline)
        verdict = check_url(current, allow_loopback)
        if not verdict.allowed:
            raise Refused(verdict.reason)
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
            headers = {"Host": parsed.netloc, "Accept": accept, **extra_headers}
            conn.request("GET", target, headers=headers)
            response = conn.getresponse()
            if response.status in _REDIRECT_CODES:
                location = response.getheader("Location")
                if not location:
                    raise Refused("redirect without Location")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise Refused(f"HTTP status {response.status}")
            content_type = response.getheader("Content-Type")
            size = int(response.getheader("Content-Length") or 0)
            verdict = validate_response(content_type, size, max_bytes)
            if not verdict.allowed:
                raise Refused(verdict.reason)
            data = _read_limited(response, max_bytes, deadline)
            return SafeResponse(data=data, content_type=content_type, final_url=current)
        finally:
            conn.close()
    raise Refused("too many redirects")


def safe_get(
    url: str,
    *,
    accept: str,
    validate_response: ResponseValidator,
    max_bytes: int,
    allow_loopback: bool = False,
    timeout: float = 10.0,
    max_redirects: int = 5,
    ca_file: str | None = None,
    deadline_seconds: float = 30.0,
    extra_headers: dict[str, str] | None = None,
) -> SafeResponse:
    """Raises on any refusal or failure. `timeout` bounds each socket operation;
    `deadline_seconds` bounds the whole fetch."""
    deadline = time.monotonic() + deadline_seconds
    return _fetch(
        url,
        accept,
        validate_response,
        allow_loopback,
        max_bytes,
        timeout,
        max_redirects,
        ca_file,
        deadline,
        extra_headers or {},
    )
