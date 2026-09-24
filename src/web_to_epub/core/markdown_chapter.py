import re
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import PurePath

import markdown
import nh3

from web_to_epub.core.models import Chapter, ImageRef

_VOID = {"br", "hr"}
_INVALID_XML = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")
_H1 = re.compile(r"<h1>(.*?)</h1>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_TAGS = nh3.ALLOWED_TAGS - {"a"}
_ATTRS = {"img": {"src", "alt", "title"}}
_SCHEMES = {"http", "https", "data"}


class _XhtmlWriter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.images: list[ImageRef] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self._image(dict(attrs))
        elif tag in _VOID:
            self.out.append(f"<{tag}/>")
        else:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag not in _VOID and tag != "img":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(escape(data, quote=False))

    def _image(self, attrs):
        src = attrs.get("src") or ""
        alt = attrs.get("alt") or ""
        caption = attrs.get("title") or None
        self.images.append(ImageRef(src, alt, caption, src.startswith(("http://", "https://"))))
        img = f'<img src="{escape(src)}" alt="{escape(alt)}"/>'
        if caption:
            img = f"<figure>{img}<figcaption>{escape(caption, quote=False)}</figcaption></figure>"
        self.out.append(img)


def parse_chapter(text: str, filename: str, strip_suffix: str | None = None) -> Chapter:
    text = _INVALID_XML.sub("", text)
    html = markdown.markdown(text, extensions=["fenced_code"])
    title = PurePath(filename).stem
    if m := _H1.search(html):
        inner = m.group(1)
        suffix = escape(strip_suffix, quote=False) if strip_suffix else ""
        if suffix and inner.endswith(suffix):
            inner = inner[: -len(suffix)]
        html = html[: m.start(1)] + inner + html[m.end(1) :]
        title = unescape(_TAG.sub("", inner))
    clean = nh3.clean(html, tags=_TAGS, attributes=_ATTRS, url_schemes=_SCHEMES)
    writer = _XhtmlWriter()
    writer.feed(clean)
    writer.close()
    return Chapter(title, "".join(writer.out), writer.images)
