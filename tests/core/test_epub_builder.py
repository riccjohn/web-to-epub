"""Tests for core.epub_builder.build_epub, verified only by reading the bytes back with ebooklib.

Interface under test (module web_to_epub.core.epub_builder):
    BookMetadata(title: str, author: str, language: str = "en", description: str = "")
    ImageData(data: bytes, media_type: str)      # e.g. ImageData(b"...", "image/png")
    build_epub(chapters: list[Chapter], metadata: BookMetadata,
               images: dict[str, ImageData], cover: ImageData | None = None) -> bytes

`images` is keyed by ImageRef.src. A src that is missing from the dict, or whose
ImageData.data is empty (failed fetch), is dropped from the chapter without breaking the build.
Chapter.body is XHTML; <img src="..."> in it is expected to be rewritten to point at the
packaged image. Zero chapters raises ValueError.
"""
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass

import ebooklib
import pytest
from ebooklib import epub
from hypothesis import given, settings, strategies as st

from web_to_epub.core.epub_builder import BookMetadata, ImageData, build_epub
from web_to_epub.core.models import Chapter, ImageRef

PNG = b"\x89PNG\r\n\x1a\n" + b"fakepng-payload"
JPG = b"\xff\xd8\xff" + b"fakejpg-payload"
META = BookMetadata(title="My Book", author="Jane Doe", language="en", description="A test book")


@dataclass
class Read:
    raw: bytes
    book: epub.EpubBook

    @property
    def chapters(self):
        docs = {i.get_name(): i for i in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
        out = []
        for idref, _ in self.book.spine:
            item = self.book.get_item_with_id(idref)
            if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT and not isinstance(item, epub.EpubNav):
                out.append(item)
        assert all(i.get_name() in docs for i in out)
        return out

    @property
    def toc_titles(self):
        def walk(entries):
            for e in entries:
                if isinstance(e, (tuple, list)):
                    yield from walk([e[0]])
                    yield from walk(e[1])
                else:
                    yield e.title
        return list(walk(self.book.toc))

    def meta(self, name, ns="DC"):
        vals = self.book.get_metadata(ns, name)
        return vals[0][0] if vals else None

    def images(self):
        return {posixpath.basename(i.get_name()): i for i in self.book.get_items_of_type(ebooklib.ITEM_IMAGE)}


def read(raw: bytes) -> Read:
    assert zipfile.is_zipfile(io.BytesIO(raw)), "build_epub must return a zip/EPUB, got %d bytes" % len(raw)
    return Read(raw, epub.read_epub(io.BytesIO(raw)))


def ch(title, body=None, images=()):
    return Chapter(title=title, body=body if body is not None else f"<h1>{title}</h1><p>text of {title}</p>", images=list(images))


def img_body(*srcs):
    return "<h1>T</h1>" + "".join(f'<p><img src="{s}" alt="a"/></p>' for s in srcs)


def srcs_of(item):
    return re.findall(r'<img[^>]*\ssrc="([^"]*)"', item.get_content().decode("utf-8"))


# STRUCTURE

def test_n_chapters_become_n_documents_in_order():
    chapters = [ch("One"), ch("Two"), ch("Three")]
    r = read(build_epub(chapters, META, {}))
    docs = r.chapters
    assert len(docs) == 3
    for doc, title in zip(docs, ["One", "Two", "Three"]):
        assert f"text of {title}" in doc.get_content().decode("utf-8")


def test_toc_has_entry_per_chapter_in_order():
    r = read(build_epub([ch("Alpha"), ch("Beta"), ch("Gamma")], META, {}))
    assert r.toc_titles == ["Alpha", "Beta", "Gamma"]


def test_metadata_round_trips():
    r = read(build_epub([ch("One")], META, {}))
    assert r.meta("title") == "My Book"
    assert r.meta("creator") == "Jane Doe"
    assert r.meta("language") == "en"
    assert r.meta("description") == "A test book"


def test_zero_chapters_raises_clear_error():
    with pytest.raises(ValueError, match="(?i)chapter"):
        build_epub([], META, {})


# IMAGES

def test_referenced_images_are_packaged_and_src_points_at_them():
    a, b = "https://x.test/a.png", "https://x.test/b.jpg"
    chapters = [ch("One", img_body(a, b), [ImageRef(a), ImageRef(b)])]
    images = {a: ImageData(PNG, "image/png"), b: ImageData(JPG, "image/jpeg")}
    r = read(build_epub(chapters, META, images))
    pkg = r.images()
    assert len(pkg) == 2
    srcs = srcs_of(r.chapters[0])
    assert len(srcs) == 2
    payloads = {pkg[posixpath.basename(s)].get_content() for s in srcs}
    assert payloads == {PNG, JPG}


def test_image_with_empty_bytes_is_dropped_but_build_succeeds():
    ok, bad = "https://x.test/ok.png", "https://x.test/bad.png"
    chapters = [ch("One", img_body(ok, bad), [ImageRef(ok), ImageRef(bad)])]
    images = {ok: ImageData(PNG, "image/png"), bad: ImageData(b"", "image/png")}
    r = read(build_epub(chapters, META, images))
    srcs = srcs_of(r.chapters[0])
    assert len(srcs) == 1
    assert len(r.images()) == 1
    assert r.images()[posixpath.basename(srcs[0])].get_content() == PNG
    assert bad not in r.chapters[0].get_content().decode("utf-8")


def test_image_missing_from_mapping_is_dropped_but_build_succeeds():
    gone = "https://x.test/gone.png"
    r = read(build_epub([ch("One", img_body(gone), [ImageRef(gone)])], META, {}))
    assert srcs_of(r.chapters[0]) == []
    assert len(r.chapters) == 1


# COVER

def test_cover_is_registered_as_cover_image():
    r = read(build_epub([ch("One")], META, {}, cover=ImageData(JPG, "image/jpeg")))
    cover_id = r.meta("cover", "OPF")
    items = [i for i in r.book.get_items() if i.get_type() == ebooklib.ITEM_COVER or "cover-image" in (getattr(i, "properties", None) or [])]
    if cover_id:
        by_id = r.book.get_item_with_id(cover_id[1]["content"] if isinstance(cover_id, tuple) else cover_id)
        if by_id is not None:
            items.append(by_id)
    assert any(i.get_content() == JPG for i in items), "no cover image with the supplied bytes"


def test_absent_cover_is_fine():
    r = read(build_epub([ch("One")], META, {}, cover=None))
    assert len(r.chapters) == 1


# STYLESHEET

def test_stylesheet_included_and_linked_from_every_chapter():
    r = read(build_epub([ch("One"), ch("Two")], META, {}))
    styles = [i for i in r.book.get_items_of_type(ebooklib.ITEM_STYLE)]
    assert styles, "no stylesheet in package"
    assert b"font-family" in styles[0].get_content()
    z = zipfile.ZipFile(io.BytesIO(r.raw))
    entries = z.namelist()
    style_entries = {e for e in entries for s in styles if e == s.get_name() or e.endswith("/" + s.get_name())}
    assert style_entries, "stylesheet not found in zip entries"
    for doc in r.chapters:
        # ebooklib drops <link> on read-back, so inspect the raw zip entry.
        matches = [e for e in entries if e == doc.get_name() or e.endswith("/" + doc.get_name())]
        assert len(matches) == 1, f"chapter entry not found in zip: {doc.get_name()}"
        entry = matches[0]
        xhtml = z.read(entry).decode("utf-8")
        hrefs = re.findall(r'<link\b[^>]*\bhref="([^"]+)"', xhtml)
        resolved = {posixpath.normpath(posixpath.join(posixpath.dirname(entry), h)) for h in hrefs}
        assert resolved & style_entries, f"{entry} does not link the stylesheet (links: {hrefs})"


# CONTAINER

def test_mimetype_is_first_entry_stored_uncompressed():
    raw = build_epub([ch("One")], META, {})
    assert zipfile.is_zipfile(io.BytesIO(raw))
    z = zipfile.ZipFile(io.BytesIO(raw))
    first = z.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype") == b"application/epub+zip"


# PROPERTIES

titles = st.lists(st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=12),
                  min_size=1, max_size=8)


@settings(max_examples=25, deadline=None)
@given(titles)
def test_output_order_equals_input_order(ts):
    r = read(build_epub([ch(t) for t in ts], META, {}))
    assert r.toc_titles == ts
    assert len(r.chapters) == len(ts)
    for doc, t in zip(r.chapters, ts):
        assert f"text of {t}" in doc.get_content().decode("utf-8")


def test_building_twice_gives_same_chapters_toc_metadata():
    chapters = [ch("One"), ch("Two")]
    r1 = read(build_epub(chapters, META, {}))
    r2 = read(build_epub(chapters, META, {}))
    assert [d.get_content() for d in r1.chapters] == [d.get_content() for d in r2.chapters]
    assert r1.toc_titles == r2.toc_titles == ["One", "Two"]
    for name in ("title", "creator", "language", "description"):
        assert r1.meta(name) == r2.meta(name) is not None


# REVIEW FIXES

def test_image_src_containing_ampersand_is_packaged():
    url = "http://x.test/y.png?a=1&b=2"
    chapters = [ch("One", img_body(url.replace("&", "&amp;")), [ImageRef(url)])]
    r = read(build_epub(chapters, META, {url: ImageData(PNG, "image/png")}))
    assert len(r.images()) == 1
    assert len(srcs_of(r.chapters[0])) == 1


def test_dropped_titled_image_takes_its_figure_with_it():
    gone = "http://x.test/gone.png"
    body = f'<h1>T</h1><figure><img src="{gone}" alt="a"/><figcaption>cap</figcaption></figure><p>after</p>'
    r = read(build_epub([ch("One", body, [ImageRef(gone)])], META, {}))
    content = r.chapters[0].get_content().decode("utf-8")
    assert "figure" not in content and "cap" not in content
    assert "after" in content


def test_kept_titled_image_keeps_its_figure_and_caption():
    url = "http://x.test/a.png"
    body = f'<h1>T</h1><figure><img src="{url}" alt="a"/><figcaption>cap</figcaption></figure>'
    r = read(build_epub([ch("One", body, [ImageRef(url)])], META, {url: ImageData(PNG, "image/png")}))
    content = r.chapters[0].get_content().decode("utf-8")
    assert "<figcaption>cap</figcaption>" in content
    assert len(srcs_of(r.chapters[0])) == 1


@pytest.mark.parametrize("body", ["", "   \n"])
def test_empty_chapter_body_raises_value_error(body):
    with pytest.raises(ValueError, match="(?i)empty"):
        build_epub([ch("One", body)], META, {})


@pytest.mark.parametrize("media_type", ["image/svg+xml", "image/x-icon", "image/avif", "text/plain"])
def test_unsupported_image_types_are_dropped(media_type):
    url = "http://x.test/a.img"
    r = read(build_epub([ch("One", img_body(url), [ImageRef(url)])], META, {url: ImageData(b"data", media_type)}))
    assert r.images() == {}
    assert srcs_of(r.chapters[0]) == []


def test_unsupported_cover_type_raises_value_error():
    with pytest.raises(ValueError, match="(?i)cover"):
        build_epub([ch("One")], META, {}, cover=ImageData(b"data", "application/octet-stream"))


def _identifier(raw: bytes) -> str:
    return read(raw).meta("identifier")


def test_identifier_differs_for_different_content_with_same_title_and_author():
    a = build_epub([ch("One", "<p>alpha</p>")], META, {})
    b = build_epub([ch("One", "<p>beta</p>")], META, {})
    assert _identifier(a) != _identifier(b)


def test_identifier_is_stable_for_identical_input():
    assert _identifier(build_epub([ch("One")], META, {})) == _identifier(build_epub([ch("One")], META, {}))


# LINKS

def kch(key, body):
    return Chapter(title=key, body=body, key=key)


def _hrefs(item):
    return re.findall(r'<a\b[^>]*\shref="([^"]*)"', item.get_content().decode("utf-8"))


def _resolve(item, href):
    return posixpath.normpath(posixpath.join(posixpath.dirname(item.get_name()), href.split("#")[0]))


def test_link_to_another_chapter_key_reaches_that_chapters_document():
    chapters = [kch("a.md", '<h1>A</h1><p><a href="b.md">go b</a></p>'), kch("b.md", "<h1>B</h1><p>text of B</p>")]
    r = read(build_epub(chapters, META, {}))
    first, second = r.chapters
    hrefs = _hrefs(first)
    assert len(hrefs) == 1, "link to a sibling chapter key must survive as a link"
    target = _resolve(first, hrefs[0])
    assert target == second.get_name()
    assert r.book.get_item_with_href(target) is not None
    assert "go b" in first.get_content().decode("utf-8")


def test_unknown_key_and_other_relative_hrefs_become_plain_text():
    body = (
        '<h1>A</h1><p><a href="nope.md">unk</a> <a href="../up.html">rel</a> '
        '<a href="/abs/path">root</a> <a href="mailto:a@b.c">mail</a></p>'
    )
    r = read(build_epub([kch("a.md", body)], META, {}))
    content = r.chapters[0].get_content().decode("utf-8")
    assert _hrefs(r.chapters[0]) == []
    for word in ("unk", "rel", "root", "mail"):
        assert word in content


def test_http_and_https_hrefs_are_untouched():
    body = '<h1>A</h1><p><a href="https://x.test/y">s</a> <a href="http://x.test/z">p</a></p>'
    r = read(build_epub([kch("a.md", body)], META, {}))
    assert _hrefs(r.chapters[0]) == ["https://x.test/y", "http://x.test/z"]


_KEYS = ["a.md", "b.md", "c.md"]
_HREFS = st.sampled_from(
    _KEYS + ["zzz.md", "../x.html", "/root", "mailto:a@b.c", "https://x.test/p", "http://x.test/q", "javascript:1"]
)


@settings(max_examples=40, deadline=None)
@given(hrefs=st.lists(st.lists(_HREFS, max_size=4), min_size=1, max_size=3))
def test_every_href_is_absolute_http_or_resolves_to_a_document_in_the_epub(hrefs):
    chapters = [
        kch(_KEYS[i], f"<h1>C{i}</h1>" + "".join(f'<p><a href="{h}">l</a></p>' for h in hs) + "<p>x</p>")
        for i, hs in enumerate(hrefs)
    ]
    r = read(build_epub(chapters, META, {}))
    names = {i.get_name() for i in r.book.get_items()}
    for doc in r.chapters:
        for href in _hrefs(doc):
            if href.startswith(("http://", "https://")):
                continue
            assert _resolve(doc, href) in names, f"dangling href {href!r} in {doc.get_name()}"


def test_link_to_another_chapter_with_fragment_still_resolves():
    chapters = [kch("a.md", '<h1>A</h1><p><a href="b.md#part">go b</a></p>'), kch("b.md", "<h1>B</h1><p>B</p>")]
    r = read(build_epub(chapters, META, {}))
    first, second = r.chapters
    hrefs = _hrefs(first)
    assert len(hrefs) == 1
    assert _resolve(first, hrefs[0]) == second.get_name()
