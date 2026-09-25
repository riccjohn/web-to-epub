import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify

from web_to_epub.core.url_list import normalize_url

_CHROME_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe"]


@dataclass(frozen=True)
class PageMarkdown:
    title: str
    markdown: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def page_to_markdown(html, page_url, chapter_files=None):
    soup = BeautifulSoup(html, "html5lib")

    base = page_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        base = urljoin(page_url, base_tag["href"])

    for tag in soup.find_all(_CHROME_TAGS):
        tag.decompose()

    content = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    self_key = normalize_url(page_url) if chapter_files else None
    for a in content.find_all("a", href=True):
        raw = a["href"].strip()
        if chapter_files and raw.startswith("#"):
            a.unwrap()
            continue
        href = urljoin(base, raw)
        if urlparse(href).scheme in ("http", "https"):
            key = normalize_url(href) if chapter_files else None
            if key in (chapter_files or {}) and key != self_key:
                a["href"] = chapter_files[key]
            else:
                a["href"] = href
        else:
            a.unwrap()
    for img in content.find_all("img", src=True):
        img["src"] = urljoin(base, img["src"].strip())

    title = ""
    h1 = content.find("h1")
    if h1:
        title = _clean(h1.get_text())
        h1.decompose()
    for extra in content.find_all("h1"):
        extra.name = "h2"
    if not title and soup.title:
        title = _clean(soup.title.get_text())
    if not title:
        title = urlparse(page_url).path.rstrip("/").rsplit("/", 1)[-1] or "Untitled"

    body = markdownify(str(content), heading_style="ATX").strip()
    return PageMarkdown(title=title, markdown=f"# {title}\n\n{body}" if body else f"# {title}")
