"""L3 tests for the HTML page fetcher against a REAL local HTTP server.

Interface under test (web_to_epub.shell.page_fetcher):

    fetch_page(url, *, allow_loopback_for_tests=False, max_bytes=<default>,
               timeout=10.0, max_redirects=5, ca_file=None,
               deadline_seconds=30.0) -> PageResult

    PageResult(page: FetchedPage | None, warning: FetchWarning | None)
        exactly one is set.
    FetchedPage(data: bytes, content_type: str, final_url: str)
        content_type is the raw Content-Type header; final_url is the URL after
        redirects (so relative links resolve against it).
    FetchWarning is web_to_epub.shell.image_fetcher.FetchWarning; warning.url is
    the URL passed in.
    Never raises.
"""

import http.server
import socket
import threading
import time

import pytest

from web_to_epub.shell.image_fetcher import FetchWarning
from web_to_epub.shell.page_fetcher import FetchedPage, PageResult, fetch_page

HTML = b"<html><body><h1>Hi</h1></body></html>"
BIG_TOTAL = 64 * 1024 * 1024


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        srv = self.server
        srv.requests.append(self.path)
        srv.headers_seen.append(dict(self.headers))
        p = self.path
        if p == "/page":
            self._send(200, "text/html; charset=utf-8", HTML)
        elif p == "/xhtml":
            self._send(200, "application/xhtml+xml", HTML)
        elif p == "/img":
            self._send(200, "image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        elif p == "/pdf":
            self._send(200, "application/pdf", b"%PDF-1.4 fake")
        elif p == "/redir":
            self._send(302, "text/plain", b"", {"Location": "/dir/final"})
        elif p == "/dir/final":
            self._send(200, "text/html", HTML)
        elif p == "/redir-blocked":
            self._send(302, "text/plain", b"", {"Location": "http://169.254.169.254/x"})
        elif p == "/loop":
            self._send(302, "text/plain", b"", {"Location": "/loop"})
        elif p == "/declared-big":
            self._send(200, "text/html", b"x" * 5000)
        elif p == "/big":
            self._big()
        elif p == "/drip":
            self._drip()
        else:
            self._send(404, "text/html", b"<html>nope</html>")

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
        self.send_header("Content-Type", "text/html")
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
        self.send_header("Content-Type", "text/html")
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
        self.headers_seen: list[dict] = []
        self.sent = 0
        self.stop = threading.Event()


@pytest.fixture
def server():
    srv = _Server(("127.0.0.1", 0))
    t = threading.Thread(
        target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    t.start()
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
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
    return fetch_page(url, **kw)


def _assert_warning(result: PageResult, url: str):
    assert result.page is None
    assert isinstance(result.warning, FetchWarning)
    assert result.warning.url == url
    assert result.warning.reason


def test_html_200_returns_bytes_content_type_and_final_url(server):
    url = server.base + "/page"
    result = _fetch(url)
    assert result.warning is None
    assert result.page == FetchedPage(
        data=HTML, content_type="text/html; charset=utf-8", final_url=url
    )


def test_xhtml_200_is_accepted(server):
    url = server.base + "/xhtml"
    result = _fetch(url)
    assert result.warning is None
    assert result.page == FetchedPage(
        data=HTML, content_type="application/xhtml+xml", final_url=url
    )


def test_redirect_followed_and_final_url_returned(server):
    result = _fetch(server.base + "/redir")
    assert result.warning is None
    assert result.page is not None
    assert result.page.final_url == server.base + "/dir/final"
    assert result.page.data == HTML
    assert server.requests == ["/redir", "/dir/final"]


def test_sends_identifying_user_agent_and_html_preferring_accept(server):
    _fetch(server.base + "/page")
    assert server.headers_seen, "no request reached the server"
    headers = {k.lower(): v for k, v in server.headers_seen[0].items()}
    ua = headers.get("user-agent", "")
    assert "web-to-epub" in ua.lower()
    accept = headers.get("accept", "")
    first = accept.split(",")[0].split(";")[0].strip()
    assert first in ("text/html", "application/xhtml+xml")


@pytest.mark.parametrize("path", ["/img", "/pdf"])
def test_non_html_content_type_refused(server, path):
    url = server.base + path
    _assert_warning(_fetch(url), url)


def test_http_error_status_refused(server):
    url = server.base + "/missing"
    _assert_warning(_fetch(url), url)


def test_declared_oversize_refused(server):
    url = server.base + "/declared-big"
    _assert_warning(_fetch(url, max_bytes=1000), url)


def test_streamed_oversize_aborted_before_full_download(server):
    url = server.base + "/big"
    _assert_warning(_fetch(url, max_bytes=1000), url)
    time.sleep(0.3)
    assert server.sent < BIG_TOTAL


def test_redirect_loop_cut_off(server):
    url = server.base + "/loop"
    _assert_warning(_fetch(url, max_redirects=3), url)
    assert 1 <= len(server.requests) <= 5


def test_redirect_to_non_public_address_refused(server):
    url = server.base + "/redir-blocked"
    _assert_warning(_fetch(url), url)
    assert server.requests == ["/redir-blocked"]


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/a", "gopher://x/", "", "not a url", "http://[bad"],
)
def test_non_http_schemes_and_malformed_urls_return_warning(url):
    _assert_warning(fetch_page(url, timeout=1.0), url)


def test_loopback_refused_without_test_flag_and_no_request_sent(server):
    url = server.base + "/page"
    _assert_warning(fetch_page(url, timeout=2.0), url)
    time.sleep(0.1)
    assert server.requests == []


def test_connection_refused_is_a_warning():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}/page"
    _assert_warning(_fetch(url), url)


def test_slow_drip_cut_off_by_total_deadline(server):
    url = server.base + "/drip"
    started = time.monotonic()
    result = _fetch(url, timeout=2.0, deadline_seconds=0.5)
    assert time.monotonic() - started < 2.0
    _assert_warning(result, url)
    assert "time" in result.warning.reason.lower()
