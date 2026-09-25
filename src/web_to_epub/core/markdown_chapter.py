import re
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import PurePath

import markdown
import nh3

from web_to_epub.core.models import Chapter, ImageRef

_VOID = {"area", "base", "br", "col", "embed", "hr", "input", "link", "meta", "source", "track", "wbr"}
_INVALID_XML = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")
_H1 = re.compile(r"<h1>(.*?)</h1>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_LINKED_IMG = re.compile(r"<a\b[^>]*>(\s*<img\b[^>]*>\s*)</a>", re.IGNORECASE)
_ATTRS = {
    "a": {"href"},
    "img": {"src", "alt", "title"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "ol": {"start"},
}
_SCHEMES = {"http", "https", "data"}


def _filter_attribute(tag, attr, value):
    if tag == "a" and value.strip().lower().startswith("data:"):
        return None
    return value


class _XhtmlWriter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.images: list[ImageRef] = []
        self._anchors: list[bool] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._anchors.append("href" in dict(attrs))
            if self._anchors[-1]:
                self.out.append(f'<a href="{escape(dict(attrs)["href"] or "")}">')
        elif tag == "img":
            self._image(dict(attrs))
        else:
            attributes = "".join(f' {name}="{escape(value or "")}"' for name, value in attrs)
            self.out.append(f"<{tag}{attributes}/>" if tag in _VOID else f"<{tag}{attributes}>")

    def handle_endtag(self, tag):
        if tag == "a":
            if self._anchors.pop():
                self.out.append("</a>")
        elif tag not in _VOID and tag != "img":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(escape(data, quote=False))

    def _image(self, attrs):
        src = attrs.get("src") or ""
        alt = attrs.get("alt") or ""
        caption = attrs.get("title") or None
        self.images.append(ImageRef(src, alt, caption, src.lower().startswith(("http://", "https://"))))
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
            inner = inner[: -len(suffix)].rstrip()
        html = html[: m.start(1)] + inner + html[m.end(1) :]
        title = unescape(_TAG.sub("", inner)).strip() or title
    clean = nh3.clean(html, attributes=_ATTRS, url_schemes=_SCHEMES, attribute_filter=_filter_attribute)
    clean = _LINKED_IMG.sub(r"\1", clean)
    writer = _XhtmlWriter()
    writer.feed(clean)
    writer.close()
    return Chapter(title, "".join(writer.out), writer.images, filename)
