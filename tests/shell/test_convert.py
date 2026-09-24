"""L3 tests for the convert use case, with a REAL local HTTP server for images.

Interface under test (web_to_epub.shell.convert):

    convert(files: list[tuple[str, bytes]], options: Options) -> Result | ConvertError

    files      list of (filename, raw bytes) in the order the caller received them.
    Options    frozen dataclass:
        title: str = ""                 required (blank/whitespace -> error)
        author: str = ""                required (blank/whitespace -> error)
        language: str = "en"
        description: str = ""
        strip_suffix: str | None = None applied to every chapter title
        order: list[str] | None = None  explicit filename order; must name the
                                        given files. None -> natural_sort of filenames.
        cover: ImageData | None = None  optional cover image
        max_total_bytes: int = 50 MiB   sum of file sizes above this -> error
        allow_loopback_for_tests: bool = False
                                        passed to fetch_image; default OFF (SSRF guard)
    Result(epub_bytes: bytes, warnings: list[FetchWarning])
        FetchWarning is web_to_epub.shell.image_fetcher.FetchWarning(url, reason).
    ConvertError(code: str, message: str, filename: str | None = None)
        codes: "no_files", "not_utf8" (filename set), "unsupported_type"
        (filename set), "too_large", "missing_title", "missing_author".
        Errors are returned, never raised.

Accepted extensions (case-insensitive): .md, .markdown, .txt.
Output is verified by reading the EPUB back with ebooklib.
"""

import http.server
import io
import threading

import pytest
from ebooklib import epub, ITEM_COVER, ITEM_DOCUMENT, ITEM_IMAGE

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.shell.convert import ConvertError, Options, Result, convert

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x02" * 64
COVER = ImageData(data=b"\x89PNG\r\n\x1a\n" + b"\x03" * 32, media_type="image/png")


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        data = {"/a.png": PNG, "/b.png": PNG2}.get(self.path)
        if data is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def base_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def opts(**kw):
    base = dict(title="Book", author="Ann")
    base.update(kw)
    return Options(**base)


def md(title, body=""):
    return f"# {title}\n\n{body}\n".encode()


def read(result) -> epub.EpubBook:
    assert isinstance(result, Result), result
    return epub.read_epub(io.BytesIO(result.epub_bytes))


def chapter_titles(book):
    return [i.title for i in book.get_items_of_type(ITEM_DOCUMENT) if i.title and i.title != "Navigation"] or [
        t.title for t in book.toc
    ]


def toc_titles(book):
    return [t.title for t in book.toc]


def covers(book):
    return [i.get_content() for i in book.get_items_of_type(ITEM_COVER)]


def images(book):
    return [i.get_content() for i in book.get_items_of_type(ITEM_IMAGE)]


def test_chapters_follow_natural_filename_order_by_default():
    files = [
        ("ch10.md", md("Ten")),
        ("ch2.md", md("Two")),
        ("ch1.md", md("One")),
    ]
    book = read(convert(files, opts()))
    assert toc_titles(book) == ["One", "Two", "Ten"]


def test_chapters_follow_caller_specified_order():
    files = [
        ("a.md", md("Alpha")),
        ("b.md", md("Bravo")),
        ("c.md", md("Charlie")),
    ]
    book = read(convert(files, opts(order=["c.md", "a.md", "b.md"])))
    assert toc_titles(book) == ["Charlie", "Alpha", "Bravo"]


def test_spine_order_matches_toc_order():
    files = [("b.md", md("Bravo", "bbb")), ("a.md", md("Alpha", "aaa"))]
    book = read(convert(files, opts(order=["b.md", "a.md"])))
    ids = [s[0] for s in book.spine if s[0] != "nav"]
    bodies = [book.get_item_with_id(i).get_content().decode() for i in ids]
    assert "bbb" in bodies[0] and "aaa" in bodies[1]


def test_metadata_and_optional_cover():
    files = [("a.md", md("Alpha"))]
    result = convert(
        files, opts(title="My Book", author="Zed", description="About", cover=COVER)
    )
    book = read(result)
    assert book.get_metadata("DC", "title")[0][0] == "My Book"
    assert book.get_metadata("DC", "creator")[0][0] == "Zed"
    assert covers(book) == [COVER.data]


def test_cover_is_optional():
    book = read(convert([("a.md", md("Alpha"))], opts()))
    assert images(book) == []


def test_txt_and_markdown_extensions_accepted():
    files = [("a.txt", b"# Aye\n\ntext"), ("b.markdown", md("Bee")), ("c.MD", md("Sea"))]
    book = read(convert(files, opts()))
    assert toc_titles(book) == ["Aye", "Bee", "Sea"]


def test_strip_suffix_applied_to_all_chapter_titles():
    files = [("a.md", md("Alpha - Site")), ("b.md", md("Bravo - Site"))]
    book = read(convert(files, opts(strip_suffix=" - Site")))
    assert toc_titles(book) == ["Alpha", "Bravo"]


def test_remote_images_are_fetched_and_embedded(base_url):
    body = f"![one]({base_url}/a.png)\n\n![two]({base_url}/b.png)"
    result = convert(
        [("a.md", md("Alpha", body))], opts(allow_loopback_for_tests=True)
    )
    book = read(result)
    assert result.warnings == []
    assert sorted(images(book)) == sorted([PNG, PNG2])


def test_failing_image_warns_with_url_and_book_still_builds(base_url):
    bad = f"{base_url}/missing.png"
    body = f"![ok]({base_url}/a.png)\n\n![bad]({bad})"
    result = convert(
        [("a.md", md("Alpha", body)), ("b.md", md("Bravo"))],
        opts(allow_loopback_for_tests=True),
    )
    book = read(result)
    assert [w.url for w in result.warnings] == [bad]
    assert toc_titles(book) == ["Alpha", "Bravo"]
    assert images(book) == [PNG]


def test_loopback_images_refused_by_default(base_url):
    url = f"{base_url}/a.png"
    result = convert([("a.md", md("Alpha", f"![x]({url})"))], opts())
    book = read(result)
    assert [w.url for w in result.warnings] == [url]
    assert images(book) == []


def test_no_files_is_error():
    err = convert([], opts())
    assert isinstance(err, ConvertError) and err.code == "no_files"


def test_non_utf8_file_error_names_the_file():
    err = convert([("ok.md", md("Ok")), ("bad.md", b"\xff\xfe\x00bad")], opts())
    assert isinstance(err, ConvertError)
    assert err.code == "not_utf8"
    assert err.filename == "bad.md"


def test_unsupported_extension_error_names_the_file():
    err = convert([("ok.md", md("Ok")), ("pic.png", b"abc")], opts())
    assert isinstance(err, ConvertError)
    assert err.code == "unsupported_type"
    assert err.filename == "pic.png"


def test_total_size_over_limit_is_error():
    files = [("a.md", b"x" * 600), ("b.md", b"y" * 600)]
    err = convert(files, opts(max_total_bytes=1000))
    assert isinstance(err, ConvertError) and err.code == "too_large"


def test_total_size_at_limit_is_ok():
    files = [("a.md", md("A"))]
    size = len(files[0][1])
    assert isinstance(convert(files, opts(max_total_bytes=size)), Result)


@pytest.mark.parametrize("title", ["", "   "])
def test_missing_title_is_error(title):
    err = convert([("a.md", md("A"))], opts(title=title))
    assert isinstance(err, ConvertError) and err.code == "missing_title"


@pytest.mark.parametrize("author", ["", "   "])
def test_missing_author_is_error(author):
    err = convert([("a.md", md("A"))], opts(author=author))
    assert isinstance(err, ConvertError) and err.code == "missing_author"


@pytest.mark.parametrize(
    "files, order, offender",
    [
        ([("a.md", md("A"))], ["nope.md"], "nope.md"),
        ([("a.md", md("A"))], ["a.md", "a.md"], "a.md"),
        ([("a.md", md("A")), ("b.md", md("B"))], ["a.md"], "b.md"),
    ],
    ids=["unknown_entry", "duplicate_entry", "file_missing_from_order"],
)
def test_bad_order_is_error_naming_offender(files, order, offender):
    err = convert(files, opts(order=order))
    assert isinstance(err, ConvertError)
    assert err.code == "bad_order"
    assert err.filename == offender or offender in err.message
