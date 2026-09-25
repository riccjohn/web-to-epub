"""Pure EPUB assembly: chapters + images in, EPUB bytes out."""
import hashlib
import io
import re
import uuid
from html import unescape
from dataclasses import dataclass

from ebooklib import epub

from web_to_epub.core.image_policy import IMAGE_EXTENSIONS
from web_to_epub.core.models import Chapter
from web_to_epub.core.styles import STYLESHEET

# A titled image is wrapped in a <figure>; when the image is dropped the whole figure goes.
_IMG_TAG = re.compile(
    r"<figure>(?P<fig_img><img\b[^>]*>)(?P<caption><figcaption>.*?</figcaption>)</figure>|(?P<img><img\b[^>]*>)",
    re.IGNORECASE | re.DOTALL,
)
_ANCHOR = re.compile(r"<a\b[^>]*>|</a>", re.IGNORECASE)
_HREF_ATTR = re.compile(r'\shref="([^"]*)"')
_SRC_ATTR = re.compile(r'\bsrc="([^"]*)"')


@dataclass(frozen=True)
class BookMetadata:
    title: str
    author: str
    language: str = "en"
    description: str = ""


@dataclass(frozen=True)
class ImageData:
    data: bytes
    media_type: str


def _identifier(chapters: list[Chapter], metadata: BookMetadata) -> str:
    """Stable for identical input, distinct for different books that share title and author."""
    digest = hashlib.sha256()
    for part in (metadata.title, metadata.author, metadata.language, *(c.title + "\0" + c.body for c in chapters)):
        digest.update(part.encode("utf-8"))
        digest.update(b"\xff")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest.hexdigest()))


def build_epub(
    chapters: list[Chapter],
    metadata: BookMetadata,
    images: dict[str, ImageData],
    cover: ImageData | None = None,
) -> bytes:
    if not chapters:
        raise ValueError("build_epub requires at least one chapter")
    for chapter in chapters:
        if not chapter.body.strip():
            raise ValueError(f"chapter {chapter.title!r} is empty")
    if cover is not None and cover.media_type not in IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported cover image type: {cover.media_type!r}")

    book = epub.EpubBook()
    book.set_identifier(_identifier(chapters, metadata))
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    book.add_author(metadata.author)
    if metadata.description:
        book.add_metadata("DC", "description", metadata.description)
    if cover is not None:
        book.set_cover(f"cover.{IMAGE_EXTENSIONS[cover.media_type]}", cover.data, create_page=False)

    style = epub.EpubItem(uid="style", file_name="style/main.css", media_type="text/css", content=STYLESHEET)
    book.add_item(style)

    packaged: dict[str, str] = {}

    def rewrite_tag(tag: str) -> str | None:
        src_match = _SRC_ATTR.search(tag)
        if src_match is None:
            return None
        src = unescape(src_match.group(1))  # the body is escaped XHTML; `images` is keyed by the raw src
        image = images.get(src)
        if image is None or not image.data or image.media_type not in IMAGE_EXTENSIONS:
            return None
        if src not in packaged:
            name = f"images/img{len(packaged) + 1}.{IMAGE_EXTENSIONS[image.media_type]}"
            packaged[src] = name
            book.add_item(epub.EpubItem(uid=f"img{len(packaged)}", file_name=name, media_type=image.media_type, content=image.data))
        return tag[: src_match.start()] + f'src="../{packaged[src]}"' + tag[src_match.end():]

    def rewrite(match: re.Match) -> str:
        rewritten = rewrite_tag(match.group("fig_img") or match.group("img"))
        if rewritten is None:
            return ""
        if match.group("fig_img"):
            return f"<figure>{rewritten}{match.group('caption')}</figure>"
        return rewritten

    targets = {c.key: f"chapter{i}.xhtml" for i, c in enumerate(chapters, start=1) if c.key}

    def resolve_links(body: str) -> str:
        open_anchors: list[bool] = []

        def rewrite_anchor(match: re.Match) -> str:
            tag = match.group(0)
            if tag.startswith("</"):
                return "</a>" if open_anchors.pop() else ""
            href_match = _HREF_ATTR.search(tag)
            href = unescape(href_match.group(1)) if href_match else ""
            if href.startswith(("http://", "https://")):
                open_anchors.append(True)
                return tag
            if href in targets:
                open_anchors.append(True)
                return f'<a href="{targets[href]}">'
            open_anchors.append(False)
            return ""

        return _ANCHOR.sub(rewrite_anchor, body)

    items = []
    for index, chapter in enumerate(chapters, start=1):
        item = epub.EpubHtml(title=chapter.title, file_name=f"text/chapter{index}.xhtml", lang=metadata.language)
        item.set_content(_IMG_TAG.sub(rewrite, resolve_links(chapter.body)))
        item.add_link(href="../style/main.css", rel="stylesheet", type="text/css")
        book.add_item(item)
        items.append(item)

    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()
