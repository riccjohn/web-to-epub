"""Pure EPUB assembly: chapters + images in, EPUB bytes out."""
import io
import re
import uuid
from dataclasses import dataclass

from ebooklib import epub

from web_to_epub.core.models import Chapter
from web_to_epub.core.styles import STYLESHEET

_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_ATTR = re.compile(r'\bsrc="([^"]*)"')
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/svg+xml": "svg", "image/webp": "webp"}


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


def _extension(image: ImageData) -> str:
    return _EXTENSIONS.get(image.media_type, "bin")


def build_epub(
    chapters: list[Chapter],
    metadata: BookMetadata,
    images: dict[str, ImageData],
    cover: ImageData | None = None,
) -> bytes:
    if not chapters:
        raise ValueError("build_epub requires at least one chapter")

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{metadata.title}|{metadata.author}")))
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    book.add_author(metadata.author)
    if metadata.description:
        book.add_metadata("DC", "description", metadata.description)
    if cover is not None:
        book.set_cover(f"cover.{_extension(cover)}", cover.data, create_page=False)

    style = epub.EpubItem(uid="style", file_name="style/main.css", media_type="text/css", content=STYLESHEET)
    book.add_item(style)

    packaged: dict[str, str] = {}

    def rewrite(match: re.Match) -> str:
        tag = match.group(0)
        src_match = _SRC_ATTR.search(tag)
        image = images.get(src_match.group(1)) if src_match else None
        if image is None or not image.data:
            return ""
        src = src_match.group(1)
        if src not in packaged:
            name = f"images/img{len(packaged) + 1}.{_extension(image)}"
            packaged[src] = name
            book.add_item(epub.EpubItem(uid=f"img{len(packaged)}", file_name=name, media_type=image.media_type, content=image.data))
        return tag[: src_match.start()] + f'src="../{packaged[src]}"' + tag[src_match.end():]

    items = []
    for index, chapter in enumerate(chapters, start=1):
        item = epub.EpubHtml(title=chapter.title, file_name=f"text/chapter{index}.xhtml", lang=metadata.language)
        item.set_content(_IMG_TAG.sub(rewrite, chapter.body))
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
