"""L4 tests for the HTTP routes, using the Flask test client (no network).

Interface under test (web_to_epub.shell.app):

    create_app(config: dict | None = None) -> flask.Flask
        `config` is applied via app.config.update(...); tests use it to set a
        small MAX_CONTENT_LENGTH. Default bind is 127.0.0.1 (not tested here).

    GET /          -> 200, text/html (upload UI; placeholder is fine)
    POST /convert  multipart/form-data
        files         repeated file parts
        order         JSON list of filenames (optional)
        title, author required; language, description, strip_suffix optional
        cover         optional image file part
      200: Content-Type application/epub+zip, Content-Disposition attachment
           with filename derived from title (<slug>.epub), body is an EPUB,
           X-Warnings header = number of image-fetch warnings (as a string).
      400: JSON {"error": "<message>"} for no files, non-UTF-8, wrong file
           type, missing title/author, malformed order.
      413: request exceeds MAX_CONTENT_LENGTH.
    No temp files are left in the temp dir or cwd after any request.
"""

import io
import json
import os
import tempfile

import pytest
from ebooklib import ITEM_COVER, ITEM_DOCUMENT, epub

from web_to_epub.shell.app import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x03" * 32


@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def _form(files, **fields):
    data = {k: v for k, v in fields.items() if v is not None}
    data["files"] = [(io.BytesIO(content), name) for name, content in files]
    return data


def _post(client, files, **fields):
    fields.setdefault("title", "My Book")
    fields.setdefault("author", "Ann Author")
    return client.post("/convert", data=_form(files, **fields), content_type="multipart/form-data")


def _read_epub(body: bytes, tmp_path):
    path = tmp_path / "out.epub"
    path.write_bytes(body)
    return epub.read_epub(str(path))


def _chapter_texts(book):
    return [i.get_content().decode("utf-8") for i in book.get_items_of_type(ITEM_DOCUMENT)
            if not isinstance(i, epub.EpubNav)]


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


def test_convert_returns_epub_with_headers(client, tmp_path):
    resp = _post(client, [("a.md", b"# Alpha\n\nfirst body"), ("b.md", b"# Beta\n\nsecond body")])
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/epub+zip")
    disp = resp.headers["Content-Disposition"]
    assert disp.startswith("attachment") and "my-book" in disp.lower().replace(" ", "-")
    assert disp.rstrip('"').endswith(".epub")
    assert resp.headers["X-Warnings"] == "0"
    book = _read_epub(resp.data, tmp_path)
    assert book.get_metadata("DC", "title")[0][0] == "My Book"
    assert book.get_metadata("DC", "creator")[0][0] == "Ann Author"
    texts = _chapter_texts(book)
    assert len(texts) == 2
    assert "first body" in texts[0] and "second body" in texts[1]


def test_convert_respects_order_field(client, tmp_path):
    resp = _post(
        client,
        [("a.md", b"# Alpha\n\nfirst body"), ("b.md", b"# Beta\n\nsecond body")],
        order=json.dumps(["b.md", "a.md"]),
    )
    assert resp.status_code == 200
    texts = _chapter_texts(_read_epub(resp.data, tmp_path))
    assert "second body" in texts[0] and "first body" in texts[1]


def test_convert_optional_fields_and_cover(client, tmp_path):
    data = _form(
        [("a.md", b"# Alpha - Suffix\n\nbody")],
        title="T", author="A", language="fr", description="A description",
        strip_suffix=" - Suffix",
    )
    data["cover"] = (io.BytesIO(PNG), "cover.png")
    resp = client.post("/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    book = _read_epub(resp.data, tmp_path)
    assert book.get_metadata("DC", "language")[0][0] == "fr"
    assert book.get_metadata("DC", "description")[0][0] == "A description"
    assert any(True for _ in book.get_items_of_type(ITEM_COVER))
    assert all("Suffix" not in t for t in _chapter_texts(book))


def test_warning_count_header_for_refused_remote_image(client):
    md = b"# A\n\n![x](http://127.0.0.1:1/x.png)\n"
    resp = _post(client, [("a.md", md)])
    assert resp.status_code == 200
    assert resp.headers["X-Warnings"] == "1"


def test_loopback_flag_not_exposed_as_request_field(client):
    md = b"# A\n\n![x](http://127.0.0.1:1/x.png)\n"
    resp = _post(client, [("a.md", md)], allow_loopback_for_tests="true")
    assert resp.status_code == 200
    assert resp.headers["X-Warnings"] == "1"


@pytest.mark.parametrize(
    "files, fields",
    [
        ([], {}),
        ([("a.md", b"\xff\xfe\x00bad")], {}),
        ([("a.pdf", b"hello")], {}),
        ([("a.md", b"# hi")], {"title": ""}),
        ([("a.md", b"# hi")], {"author": ""}),
        ([("a.md", b"# hi")], {"order": "not json"}),
        ([("a.md", b"# hi")], {"order": '{"a": 1}'}),
        ([("a.md", b"# hi")], {"order": '["nope.md"]'}),
        ([("a.md", b"# hi")], {"order": '["a.md", "a.md"]'}),
        ([("a.md", b"# hi"), ("b.md", b"# yo")], {"order": '["a.md"]'}),
    ],
    ids=["no_files", "bad_encoding", "wrong_type", "no_title", "no_author",
         "order_not_json", "order_not_list", "order_unknown_file",
         "order_duplicate", "order_missing_file"],
)
def test_bad_requests_return_400_json_error(client, files, fields):
    resp = _post(client, files, **fields)
    assert resp.status_code == 400
    body = resp.get_json()
    assert isinstance(body["error"], str) and body["error"]


def test_oversized_request_returns_413():
    client = create_app({"TESTING": True, "MAX_CONTENT_LENGTH": 1024}).test_client()
    resp = _post(client, [("a.md", b"x" * 10_000)])
    assert resp.status_code == 413


def _listing():
    return (
        sorted(os.listdir(tempfile.gettempdir())),
        sorted(os.listdir(os.getcwd())),
    )


@pytest.mark.parametrize("ok", [True, False], ids=["success", "error"])
def test_no_files_left_on_disk(client, ok, tmp_path, monkeypatch):
    tmp = tmp_path / "tmpdir"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.setenv("TMPDIR", str(tmp))
    before = _listing()
    files = [("a.md", b"# A\n\nbody")] if ok else [("a.pdf", b"x")]
    resp = _post(client, files)
    assert resp.status_code == (200 if ok else 400)
    assert _listing() == before
    assert os.listdir(tmp) == []


# REVIEW FIXES

def test_file_part_without_filename_returns_400(client):
    data = {"title": "T", "author": "A", "files": [(io.BytesIO(b"# hi"), "")]}
    resp = client.post("/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_empty_markdown_file_returns_400(client):
    resp = _post(client, [("a.md", b"")])
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_duplicate_filenames_return_400(client):
    resp = _post(client, [("a.md", b"# one"), ("a.md", b"# two")])
    assert resp.status_code == 400


def test_non_image_cover_returns_400(client):
    data = _form([("a.md", b"# hi")], title="T", author="A")
    data["cover"] = (io.BytesIO(b"not an image"), "cover.txt", "text/plain")
    resp = client.post("/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"]


# POST /fetch  (URL sources) -- real local fixture server, Flask test client
#
#   POST /fetch  JSON {"urls": [...]}
#     200: {"chapters": [{filename, url, title, markdown}], "errors": [{url, message}]}
#          (both keys always present)
#     400: {"error": msg} for non-JSON body, urls missing / not a list of strings,
#          empty list, over the max count (50), or an invalid URL (ftp://, no host).
#   App config ALLOW_LOOPBACK_FOR_TESTS (default False) lets /fetch AND /convert
#   image fetching reach the 127.0.0.1 fixture server. It is a config key only,
#   never a request field.

import http.server
import posixpath
import re
import threading

from ebooklib import ITEM_IMAGE

_FIXTURE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x07" * 40


def _fx_page(title, body):
    return (
        f"<html><head><title>{title}</title></head>"
        f"<body><article><h1>{title}</h1>{body}</article></body></html>"
    ).encode()


class _FxHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        base = self.server.base
        if self.path == "/a":
            body = _fx_page(
                "Alpha",
                f'<p>see <a href="{base}/b">beta</a> and '
                f'<a href="https://example.com/external">ext</a></p>'
                f'<p><img src="{base}/pic.png" alt="pic"></p>',
            )
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/b":
            body = _fx_page("Beta", f'<p>back to <a href="{base}/a">alpha</a> beta body</p>')
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/pic.png":
            self._send(200, "image/png", _FIXTURE_PNG)
        else:
            self._send(404, "text/html", b"<html>nope</html>")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def fx_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FxHandler)
    srv.daemon_threads = True
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


@pytest.fixture
def loopback_client():
    return create_app({"TESTING": True, "ALLOW_LOOPBACK_FOR_TESTS": True}).test_client()


def test_fetch_returns_chapters_in_input_order(loopback_client, fx_server):
    urls = [f"{fx_server.base}/b", f"{fx_server.base}/a"]
    resp = loopback_client.post("/fetch", json={"urls": urls})
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == {"chapters", "errors"}
    assert body["errors"] == []
    assert [c["url"] for c in body["chapters"]] == urls
    assert [c["title"] for c in body["chapters"]] == ["Beta", "Alpha"]
    for c in body["chapters"]:
        assert set(c) == {"filename", "url", "title", "markdown"}
        assert c["filename"].endswith(".md") and c["markdown"].strip()


def test_fetch_partial_failure_reports_error_and_keeps_others(loopback_client, fx_server):
    missing = f"{fx_server.base}/missing"
    resp = loopback_client.post("/fetch", json={"urls": [f"{fx_server.base}/a", missing]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert [c["title"] for c in body["chapters"]] == ["Alpha"]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["url"] == missing
    assert body["errors"][0]["message"].strip()


def test_fetch_non_public_address_is_a_per_url_error_not_a_500(client, fx_server):
    url = f"{fx_server.base}/a"  # loopback; default config forbids it
    resp = client.post("/fetch", json={"urls": [url]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["chapters"] == []
    assert [e["url"] for e in body["errors"]] == [url]
    assert body["errors"][0]["message"].strip()


def test_fetch_loopback_is_not_enabled_by_a_request_field(client, fx_server):
    url = f"{fx_server.base}/a"
    resp = client.post("/fetch", json={"urls": [url], "allow_loopback_for_tests": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["chapters"] == [] and len(body["errors"]) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "not json", "content_type": "application/json"},
        {"data": "hello", "content_type": "text/plain"},
        {"json": {}},
        {"json": {"urls": "http://example.com/"}},
        {"json": {"urls": [1, 2]}},
        {"json": {"urls": ["http://example.com/", None]}},
        {"json": {"urls": []}},
        {"json": {"urls": [f"http://example.com/{i}" for i in range(51)]}},
        {"json": {"urls": ["ftp://example.com/file"]}},
        {"json": {"urls": ["http://"]}},
        {"json": {"urls": ["http://example.com/ok", "not a url"]}},
        {"json": ["http://example.com/"]},
    ],
    ids=["bad_json", "not_json_type", "urls_missing", "urls_string", "urls_ints",
         "urls_mixed_types", "urls_empty", "over_max", "ftp_scheme", "no_host",
         "one_invalid_among_valid", "body_is_list"],
)
def test_fetch_bad_requests_return_400_json_error(client, kwargs):
    resp = client.post("/fetch", **kwargs)
    assert resp.status_code == 400
    body = resp.get_json()
    assert isinstance(body["error"], str) and body["error"]


def test_fetch_response_feeds_convert_end_to_end(loopback_client, fx_server, tmp_path):
    a_url, b_url = f"{fx_server.base}/a", f"{fx_server.base}/b"
    fetched = loopback_client.post("/fetch", json={"urls": [a_url, b_url]})
    assert fetched.status_code == 200
    chapters = fetched.get_json()["chapters"]
    assert len(chapters) == 2

    data = {
        "title": "Web Book",
        "author": "Ann Author",
        "order": json.dumps([c["filename"] for c in chapters]),
        "files": [(io.BytesIO(c["markdown"].encode("utf-8")), c["filename"]) for c in chapters],
    }
    resp = loopback_client.post("/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert resp.headers["X-Warnings"] == "0"
    book = _read_epub(resp.data, tmp_path)

    docs = [i for i in book.get_items_of_type(ITEM_DOCUMENT) if not isinstance(i, epub.EpubNav)]
    assert len(docs) == 2
    a_doc, b_doc = docs
    a_html = a_doc.get_content().decode("utf-8")

    hrefs = re.findall(r'<a\b[^>]*\shref="([^"]*)"', a_html)
    internal = [
        h for h in hrefs
        if not h.startswith(("http://", "https://")) and
        posixpath.normpath(posixpath.join(posixpath.dirname(a_doc.get_name()), h.split("#")[0]))
        == b_doc.get_name()
    ]
    assert internal, f"chapter A has no link to chapter B's document; hrefs={hrefs}"
    assert "https://example.com/external" in hrefs
    assert not any(h.startswith(fx_server.base) for h in hrefs)

    assert any(True for _ in book.get_items_of_type(ITEM_IMAGE)), "fixture image not embedded"


@pytest.mark.parametrize("urls", [["", "   "], [""], ["\t", "\n", "  "]],
                         ids=["two_blanks", "one_blank", "whitespace_kinds"])
def test_fetch_only_blank_urls_returns_400_like_empty_list(client, urls):
    resp = client.post("/fetch", json={"urls": urls})
    assert resp.status_code == 400
    body = resp.get_json()
    assert isinstance(body["error"], str) and body["error"]
