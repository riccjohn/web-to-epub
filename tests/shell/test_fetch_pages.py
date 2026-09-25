"""L3 tests for the fetch-pages use case against a REAL local HTTP server.

Interface under test (web_to_epub.shell.fetch_pages):

    fetch_pages(urls: list[str], *, allow_loopback_for_tests=False,
                max_urls=50, budget_seconds=120.0, max_workers=4,
                timeout=10.0) -> list[PageChapter | PageFailure]

    Results are in input order, one per input URL.
    PageChapter(filename, url, title, markdown)   frozen; url is as requested.
    PageFailure(url, message)                     frozen; message is readable.
    Raises ValueError when len(urls) > max_urls (before any fetching).
    Fetches concurrently (ThreadPoolExecutor, max_workers); once the budget is
    spent, remaining URLs get PageFailure(url, "skipped: fetch budget exhausted").
"""

import http.server
import threading
import time

import pytest

from web_to_epub.core.url_list import chapter_filename
from web_to_epub.shell.fetch_pages import PageChapter, PageFailure, fetch_pages


def _page(title, body):
    return (
        f"<html><head><title>{title}</title></head>"
        f"<body><article><h1>{title}</h1>{body}</article></body></html>"
    ).encode()


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        srv = self.server
        p = self.path
        base = srv.base
        if p == "/a":
            self._send(200, "text/html; charset=utf-8",
                       _page("Alpha", f'<p>see <a href="{base}/b">beta</a> and '
                                      f'<a href="{base}/unlisted">other</a></p>'))
        elif p == "/b":
            self._send(200, "text/html; charset=utf-8",
                       _page("Beta", f'<p>back to <a href="{base}/a">alpha</a></p>'))
        elif p == "/unlisted":
            self._send(200, "text/html; charset=utf-8", _page("Unlisted", "<p>x</p>"))
        elif p == "/empty":
            self._send(200, "text/html; charset=utf-8",
                       b"<html><head><title>T</title></head><body><nav>menu</nav></body></html>")
        elif p == "/cp1252":
            body = _page("Café", "<p>naïve “quote” café</p>")
            self._send(200, "text/html; charset=windows-1252", body.decode().encode("cp1252"))
        elif p == "/old":
            self._send(302, "text/plain", b"", {"Location": "/new/a"})
        elif p == "/new/a":
            self._send(200, "text/html; charset=utf-8",
                       _page("Moved", '<p><a href="sibling">sib</a></p>'))
        elif p == "/links-final":
            self._send(200, "text/html; charset=utf-8",
                       _page("LF", f'<p><a href="{base}/new/a">to final</a></p>'))
        elif p == "/links-old":
            self._send(200, "text/html; charset=utf-8",
                       _page("LO", f'<p><a href="{base}/old">to requested</a></p>'))
        elif p == "/links-empty":
            self._send(200, "text/html; charset=utf-8",
                       _page("LE", f'<p><a href="{base}/empty">to empty</a></p>'))
        elif p == "/to-empty-final":
            self._send(302, "text/plain", b"", {"Location": "/new/a"})
        elif p.startswith("/slow"):
            time.sleep(0.6)
            self._send(200, "text/html; charset=utf-8", _page("Slow", "<p>s</p>"))
        elif p.startswith("/hold"):
            with srv.lock:
                srv.inflight += 1
                srv.max_inflight = max(srv.max_inflight, srv.inflight)
            time.sleep(0.2)
            with srv.lock:
                srv.inflight -= 1
            self._send(200, "text/html; charset=utf-8", _page("Hold", "<p>h</p>"))
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


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr):
        super().__init__(addr, _Handler)
        self.lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0
        self.base = ""


@pytest.fixture
def server():
    srv = _Server(("127.0.0.1", 0))
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _run(urls, **kw):
    kw.setdefault("allow_loopback_for_tests", True)
    kw.setdefault("timeout", 2.0)
    return fetch_pages(urls, **kw)


def test_returns_one_result_per_url_in_input_order(server):
    urls = [f"{server.base}/b", f"{server.base}/a", f"{server.base}/unlisted"]
    results = _run(urls)
    assert len(results) == 3
    assert [r.url for r in results] == urls
    assert [r.title for r in results] == ["Beta", "Alpha", "Unlisted"]
    assert all(isinstance(r, PageChapter) for r in results)
    assert all(r.markdown for r in results)


def test_failure_has_url_and_message_and_does_not_affect_others(server):
    urls = [f"{server.base}/a", f"{server.base}/missing", f"{server.base}/b"]
    results = _run(urls)
    assert len(results) == 3
    assert isinstance(results[0], PageChapter)
    assert isinstance(results[2], PageChapter)
    assert isinstance(results[1], PageFailure)
    assert results[1].url == urls[1]
    assert results[1].message.strip()


def test_filenames_come_from_chapter_filename_unique_and_sorted(server):
    urls = [f"{server.base}/{n}" for n in ("b", "a", "unlisted")]
    results = _run(urls)
    names = [r.filename for r in results]
    assert names == [chapter_filename(i, u) for i, u in enumerate(urls)]
    assert len(set(names)) == len(names)
    assert names == sorted(names)


def test_links_between_listed_pages_are_rewritten_to_filenames(server):
    urls = [f"{server.base}/a", f"{server.base}/b"]
    a, b = _run(urls)
    assert f"({b.filename})" in a.markdown
    assert f"({a.filename})" in b.markdown
    assert f"{server.base}/b)" not in a.markdown


def test_link_to_unlisted_page_stays_absolute(server):
    a, _b = _run([f"{server.base}/a", f"{server.base}/b"])
    assert f"({server.base}/unlisted)" in a.markdown


def test_empty_content_is_a_failure_not_an_empty_chapter(server):
    url = f"{server.base}/empty"
    (result,) = _run([url])
    assert isinstance(result, PageFailure)
    assert result.url == url
    assert "no readable content" in result.message


def test_windows_1252_page_decodes_correctly(server):
    (result,) = _run([f"{server.base}/cp1252"])
    assert isinstance(result, PageChapter)
    assert result.title == "Café"
    assert "naïve" in result.markdown
    assert "“quote”" in result.markdown


def test_links_map_to_both_requested_and_final_url_of_a_redirect(server):
    urls = [f"{server.base}/old", f"{server.base}/links-final", f"{server.base}/links-old"]
    old, lf, lo = _run(urls)
    assert isinstance(old, PageChapter)
    assert old.url == urls[0]
    assert f"({old.filename})" in lf.markdown  # linked via the final URL
    assert f"({old.filename})" in lo.markdown  # linked via the requested URL
    # relative links in the redirected page resolve against the final URL
    assert f"({server.base}/new/sibling)" in old.markdown


def test_max_url_count_is_enforced(server):
    urls = [f"{server.base}/hold{i}" for i in range(4)]
    with pytest.raises(ValueError):
        _run(urls, max_urls=3)
    assert server.max_inflight == 0  # nothing was fetched


def test_budget_exhaustion_skips_remaining_urls(server):
    urls = [f"{server.base}/slow{i}" for i in range(3)]
    results = _run(urls, budget_seconds=0.3, max_workers=1)
    assert len(results) == 3
    for r in results[1:]:
        assert isinstance(r, PageFailure)
        assert r.message == "skipped: fetch budget exhausted"
    assert [r.url for r in results] == urls


def test_concurrency_is_bounded_by_max_workers(server):
    urls = [f"{server.base}/hold{i}" for i in range(6)]
    results = _run(urls, max_workers=2)
    assert len(results) == 6
    assert all(isinstance(r, PageChapter) for r in results)
    assert server.max_inflight == 2


def test_link_to_a_page_that_fails_conversion_stays_a_working_url(server):
    urls = [f"{server.base}/links-empty", f"{server.base}/empty"]
    linker, failed = _run(urls)
    assert isinstance(failed, PageFailure)
    assert f"({server.base}/empty)" in linker.markdown


def test_redirect_to_another_listed_page_yields_one_chapter(server):
    urls = [f"{server.base}/old", f"{server.base}/new/a", f"{server.base}/links-final"]
    old, new, lf = _run(urls)
    assert isinstance(old, PageFailure)
    assert urls[1] in old.message
    assert isinstance(new, PageChapter)
    assert f"({new.filename})" in lf.markdown  # link goes to the page's own chapter


def test_two_urls_redirecting_to_one_page_yield_one_chapter(server):
    urls = [f"{server.base}/old", f"{server.base}/to-empty-final"]
    first, second = _run(urls)
    assert isinstance(first, PageChapter)
    assert isinstance(second, PageFailure)
    assert "duplicate" in second.message
