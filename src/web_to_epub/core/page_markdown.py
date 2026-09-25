import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify

from web_to_epub.core.url_list import normalize_url

_ALWAYS_REMOVED = ["script", "style", "noscript", "iframe"]
_CHROME_TAGS = ["nav", "footer", "aside"]
_FORM_CONTROLS = ["input", "button", "select", "textarea"]


@dataclass(frozen=True)
class PageMarkdown:
    title: str
    markdown: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _safe_normalize(url):
    try:
        return normalize_url(url)
    except ValueError:
        return None


def page_to_markdown(html, page_url, chapter_files=None):
    soup = BeautifulSoup(html, "html5lib")

    base = page_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        try:
            base = urljoin(page_url, base_tag["href"])
        except ValueError:
            pass

    for tag in soup.find_all(_ALWAYS_REMOVED):
        tag.decompose()

    content = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
    )
    if content is None:
        # No content landmark: the page-level header is site chrome, not the article's.
        content = soup.body or soup
        for tag in content.find_all("header"):
            tag.decompose()
    for tag in content.find_all(_CHROME_TAGS):
        tag.decompose()
    # Some legacy pages wrap the whole body in a <form>; keep its content, drop the controls.
    for tag in content.find_all(_FORM_CONTROLS):
        tag.decompose()
    for tag in content.find_all("form"):
        tag.unwrap()

    self_key = _safe_normalize(page_url) if chapter_files else None
    for a in content.find_all("a", href=True):
        raw = a["href"].strip()
        if chapter_files and raw.startswith("#"):
            a.unwrap()
            continue
        try:
            href = urljoin(base, raw)
            scheme = urlparse(href).scheme
            key = normalize_url(href) if chapter_files and scheme in ("http", "https") else None
        except ValueError:
            a.unwrap()
            continue
        if scheme in ("http", "https"):
            if key in (chapter_files or {}) and key != self_key:
                a["href"] = chapter_files[key]
            else:
                a["href"] = href
        else:
            a.unwrap()
    for img in content.find_all("img", src=True):
        try:
            img["src"] = urljoin(base, img["src"].strip())
        except ValueError:
            del img["src"]

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
