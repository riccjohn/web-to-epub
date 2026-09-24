"""L3 tests for the image fetcher against a REAL local HTTP(S) server.

Interface under test (web_to_epub.shell.image_fetcher):

    fetch_image(url, *, allow_loopback_for_tests=False, max_bytes=10 MiB,
                timeout=10.0, max_redirects=5, ca_file=None) -> FetchResult

    FetchResult(image: ImageData | None, warning: FetchWarning | None)
        exactly one is set. ImageData is web_to_epub.core.epub_builder.ImageData
        (data: bytes, media_type: str).
    FetchWarning(url: str, reason: str)   # url = the URL passed in

    - never raises; every failure is a FetchResult with a warning.
    - allow_loopback_for_tests: default False; when True, loopback addresses
      are permitted (all other blocked ranges stay blocked).
    - max_redirects: max hops followed; each hop re-validated.
    - ca_file: optional PEM bundle to trust instead of system CAs (used to
      prove TLS verification is on by default and works when trusted).
"""

import http.server
import shutil
import socket
import ssl
import subprocess
import threading
import time

import pytest

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.shell.image_fetcher import FetchResult, fetch_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
BIG_TOTAL = 64 * 1024 * 1024


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        srv = self.server
        srv.requests.append(self.path)
        p = self.path
        if p == "/img.png":
            self._send(200, "image/png", PNG)
        elif p == "/page.html":
            self._send(200, "text/html", b"<html></html>")
        elif p == "/redir-ok":
            self._send(302, "text/plain", b"", {"Location": "/img.png"})
        elif p == "/redir-blocked":
            self._send(
                302, "text/plain", b"", {"Location": "http://169.254.169.254/x.png"}
            )
        elif p == "/loop":
            self._send(302, "text/plain", b"", {"Location": "/loop"})
        elif p == "/slow":
            srv.stop.wait(3)
            try:
                self._send(200, "image/png", PNG)
            except OSError:
                pass
        elif p == "/big":
            self._big()
        elif p == "/drip":
            self._drip()
        else:
            self._send(404, "text/plain", b"nope")

    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _drip(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", "1000")
        self.end_headers()
        try:
            for _ in range(1000):
                self.wfile.write(b"x")
                self.wfile.flush()
                if self.server.stop.wait(0.1):
                    break
        except OSError:
            pass
        self.close_connection = True

    def _big(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        chunk = b"x" * 65536
        try:
            while self.server.sent < BIG_TOTAL:
                self.wfile.write(b"10000\r\n" + chunk + b"\r\n")
                self.server.sent += len(chunk)
            self.wfile.write(b"0\r\n\r\n")
        except OSError:
            pass
        self.close_connection = True


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr):
        super().__init__(addr, _Handler)
        self.requests: list[str] = []
        self.sent = 0
        self.stop = threading.Event()


def _run(server):
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    t.start()
    return t


@pytest.fixture
def server():
    srv = _Server(("127.0.0.1", 0))
    t = _run(srv)
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        yield srv
    finally:
        srv.stop.set()
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


@pytest.fixture
def tls_server(tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl not available")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    srv = _Server(("127.0.0.1", 0))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    t = _run(srv)
    srv.base = f"https://localhost:{srv.server_address[1]}"
    srv.cert = str(cert)
    try:
        yield srv
    finally:
        srv.stop.set()
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _fetch(url, **kw):
    kw.setdefault("allow_loopback_for_tests", True)
    kw.setdefault("timeout", 2.0)
    return fetch_image(url, **kw)


def _assert_warning(result: FetchResult, url: str):
    assert result.image is None
    assert result.warning is not None
    assert result.warning.url == url
    assert result.warning.reason


def test_loopback_allowed_returns_bytes_and_content_type(server):
    result = _fetch(server.base + "/img.png")
    assert result.warning is None
    assert result.image == ImageData(data=PNG, media_type="image/png")


def test_hostname_resolved_and_fetched(server):
    port = server.server_address[1]
    result = _fetch(f"http://localhost:{port}/img.png")
    assert result.image == ImageData(data=PNG, media_type="image/png")


def test_loopback_refused_by_default_and_no_request_sent(server):
    url = server.base + "/img.png"
    result = fetch_image(url, timeout=2.0)
    _assert_warning(result, url)
    time.sleep(0.1)
    assert server.requests == []


def test_localhost_hostname_refused_by_default_and_no_request_sent(server):
    url = f"http://localhost:{server.server_address[1]}/img.png"
    result = fetch_image(url, timeout=2.0)
    _assert_warning(result, url)
    time.sleep(0.1)
    assert server.requests == []


def test_redirect_to_allowed_target_is_followed(server):
    result = _fetch(server.base + "/redir-ok")
    assert result.image == ImageData(data=PNG, media_type="image/png")
    assert server.requests == ["/redir-ok", "/img.png"]


def test_redirect_to_blocked_address_refused(server):
    url = server.base + "/redir-blocked"
    result = _fetch(url)
    _assert_warning(result, url)
    assert server.requests == ["/redir-blocked"]


def test_redirect_loop_cut_off(server):
    url = server.base + "/loop"
    result = _fetch(url, max_redirects=3)
    _assert_warning(result, url)
    assert 1 <= len(server.requests) <= 5


def test_oversize_response_aborted_before_full_download(server):
    url = server.base + "/big"
    result = _fetch(url, max_bytes=1000)
    _assert_warning(result, url)
    time.sleep(0.3)
    assert server.sent < BIG_TOTAL


def test_slow_response_times_out(server):
    url = server.base + "/slow"
    start = time.monotonic()
    result = _fetch(url, timeout=0.3)
    assert time.monotonic() - start < 2.5
    _assert_warning(result, url)


def test_non_image_content_type_rejected(server):
    url = server.base + "/page.html"
    _assert_warning(_fetch(url), url)


def test_http_error_status_is_a_warning(server):
    url = server.base + "/missing"
    _assert_warning(_fetch(url), url)


@pytest.mark.parametrize(
    "url",
    ["http://[bad", "", "not a url", "file:///etc/passwd", "ftp://example.com/a.png"],
)
def test_malformed_or_unsupported_urls_return_warning_not_raise(url):
    _assert_warning(fetch_image(url, timeout=1.0), url)


def test_connection_refused_is_a_warning():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}/a.png"
    _assert_warning(_fetch(url), url)


def test_tls_verification_on_by_default(tls_server):
    url = tls_server.base + "/img.png"
    _assert_warning(_fetch(url), url)
    assert tls_server.requests == []


def test_tls_succeeds_when_certificate_trusted(tls_server):
    result = _fetch(tls_server.base + "/img.png", ca_file=tls_server.cert)
    assert result.image == ImageData(data=PNG, media_type="image/png")


# REVIEW FIXES

def test_slow_drip_response_is_cut_off_by_total_deadline(server):
    started = time.monotonic()
    result = _fetch(server.base + "/drip", timeout=2.0, deadline_seconds=0.5)
    elapsed = time.monotonic() - started
    _assert_warning(result, server.base + "/drip")
    assert elapsed < 2.0
    assert "time" in result.warning.reason.lower()
