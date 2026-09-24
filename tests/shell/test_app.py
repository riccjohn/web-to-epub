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
