import re
from pathlib import Path

from hypothesis import given, settings, strategies as st

from web_to_epub.core.page_markdown import page_to_markdown

FIXTURES = Path(__file__).parent.parent / "fixtures"
URL = "https://example.com/blog/post.html"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _convert(html: str, url: str = URL):
    return page_to_markdown(html, url)


def _headings(md: str) -> list[str]:
    return [ln for ln in md.splitlines() if ln.startswith("# ")]


# --- content selection & chrome removal ------------------------------------


def test_semantic_article_chrome_removed():
    md = _convert(_fixture("semantic_article.html")).markdown
    for marker in [
        "Blog logo marker",
        "Archive nav marker",
        "Newsletter aside marker",
        "Footer legal marker",
        "SEMANTIC_SCRIPT_MARKER",
    ]:
        assert marker not in md
    assert "Tomatoes love" in md


def test_prefers_article_over_rest_of_body():
    html = "<body><p>Outside text</p><article><h1>T</h1><p>Inside text</p></article></body>"
    md = _convert(html).markdown
    assert "Inside text" in md
    assert "Outside text" not in md


def test_uses_main_when_no_article():
    html = "<body><div>Outside text</div><main><p>Main text</p></main></body>"
    md = _convert(html).markdown
    assert "Main text" in md
    assert "Outside text" not in md


def test_uses_role_main_when_no_article_or_main():
    html = '<body><div>Outside text</div><div role="main"><p>Role text</p></div></body>'
    md = _convert(html).markdown
    assert "Role text" in md
    assert "Outside text" not in md


def test_falls_back_to_body():
    md = _convert("<html><body><p>Only body text</p></body></html>").markdown
    assert "Only body text" in md


def test_removes_all_chrome_elements_and_contents():
    html = (
        "<body><p>Keep me</p>"
        "<script>SCRIPT_TXT</script><style>STYLE_TXT</style>"
        "<noscript>NOSCRIPT_TXT</noscript><nav>NAV_TXT</nav>"
        "<header>HEADER_TXT</header><footer>FOOTER_TXT</footer>"
        "<aside>ASIDE_TXT</aside><form>FORM_TXT<input></form>"
        "<iframe>IFRAME_TXT</iframe></body>"
    )
    md = _convert(html).markdown
    assert "Keep me" in md
    for gone in [
        "SCRIPT_TXT", "STYLE_TXT", "NOSCRIPT_TXT", "NAV_TXT",
        "HEADER_TXT", "FOOTER_TXT", "ASIDE_TXT", "FORM_TXT", "IFRAME_TXT",
    ]:
        assert gone not in md
    assert "<script" not in md.lower()


# --- messy HTML ------------------------------------------------------------


def test_messy_lesson_chrome_removed():
    md = _convert(_fixture("messy_lesson.html")).markdown
    for marker in [
        "Site menu",
        "Course banner text",
        "SCRIPT_BODY_MARKER",
        "hidden-style-marker",
        "Please enable JavaScript marker",
        "Subscribe form marker",
        "Related sidebar marker",
        "Copyright footer marker",
    ]:
        assert marker not in md
    assert "Loops let you repeat work." in md


def test_messy_lesson_lists_are_flat():
    md = _convert(_fixture("messy_lesson.html")).markdown
    bullets = [ln for ln in md.splitlines() if re.match(r"^\s*[-*+]\s+\S", ln)]
    assert [re.sub(r"^\s*[-*+]\s+", "", b).strip() for b in bullets] == [
        "for loops",
        "while loops",
        "do-while loops",
    ]
    assert all(not b.startswith((" ", "\t")) for b in bullets)
    numbered = [ln for ln in md.splitlines() if re.match(r"^\s*\d+\.\s+\S", ln)]
    assert len(numbered) == 3
    assert all(not n.startswith((" ", "\t")) for n in numbered)


def test_messy_lesson_title_and_single_heading_start():
    result = _convert(_fixture("messy_lesson.html"))
    assert result.title == "Lesson 3: Loops"
    assert result.markdown.startswith("# Lesson 3: Loops")
    assert len(_headings(result.markdown)) == 1


# --- title selection -------------------------------------------------------


def test_title_from_first_h1_over_title_tag():
    result = _convert(_fixture("semantic_article.html"))
    assert result.title == "Growing Tomatoes"
    assert result.markdown.startswith("# Growing Tomatoes")
    assert len(_headings(result.markdown)) == 1


def test_title_from_title_tag_when_no_h1():
    html = "<html><head><title>Tag Title</title></head><body><p>Body</p></body></html>"
    result = _convert(html)
    assert result.title == "Tag Title"
    assert result.markdown.startswith("# Tag Title")


def test_title_from_last_url_path_segment_when_nothing_else():
    result = _convert("<body><p>Body</p></body>", "https://example.com/docs/my-page")
    assert result.title == "my-page"
    assert result.markdown.startswith("# my-page")


def test_empty_content_yields_only_title():
    result = _convert("<html><head><title>Just Title</title></head><body></body></html>")
    assert result.markdown.strip() == "# Just Title"


# --- preserved structure ---------------------------------------------------


def test_preserves_semantic_structure():
    md = _convert(_fixture("semantic_article.html")).markdown
    assert "## Supplies" in md
    assert "*sun*" in md or "_sun_" in md
    assert "**water**" in md
    assert re.search(r"^[-*+]\s+Seeds$", md, re.M)
    assert re.search(r"^[-*+]\s+Soil$", md, re.M)
    assert re.search(r"^>\s*Patience is a gardener", md, re.M)
    assert "water(plant, liters=2)" in md
    assert "```" in md or re.search(r"^( {4}|\t)water\(plant", md, re.M)
    assert "Line one" in md and "Line two" in md
    assert "Line one Line two" not in md
    assert re.search(r"^\s*([-*_])(\s*\1){2,}\s*$", md, re.M)  # hr


def test_ordered_list_preserved():
    md = _convert("<body><ol><li>First</li><li>Second</li></ol></body>").markdown
    assert re.search(r"^1\.\s+First$", md, re.M)
    assert re.search(r"^2\.\s+Second$", md, re.M)


def test_image_alt_kept():
    md = _convert('<body><img src="/a.png" alt="Alt words"></body>').markdown
    assert "![Alt words](https://example.com/a.png)" in md


# --- absolute URLs ---------------------------------------------------------


def test_relative_urls_resolved_against_page_url():
    md = _convert(_fixture("semantic_article.html")).markdown
    assert "(https://example.com/img/tomato.png)" in md
    assert "(https://example.com/blog/guide/soil.html)" in md


def test_parent_relative_link_resolved():
    md = _convert(_fixture("messy_lesson.html"), "https://ex.org/a/b/lesson3.html").markdown
    assert "(https://ex.org/a/lesson2.html)" in md


def test_base_href_honored():
    html = (
        '<html><head><base href="https://cdn.example.org/root/"></head>'
        '<body><a href="page.html">L</a><img src="p.png" alt="I"></body></html>'
    )
    md = _convert(html).markdown
    assert "(https://cdn.example.org/root/page.html)" in md
    assert "(https://cdn.example.org/root/p.png)" in md


def test_javascript_and_mailto_links_become_plain_text():
    html = (
        '<body><a href="javascript:alert(1)">JS link</a> '
        '<a href="mailto:a@b.com">Mail me</a></body>'
    )
    md = _convert(html).markdown
    assert "JS link" in md and "Mail me" in md
    assert "javascript:" not in md
    assert "mailto:" not in md
    assert "](" not in md


def test_data_uri_images_kept():
    src = "data:image/png;base64,iVBORw0KGgo="
    md = _convert(f'<body><img src="{src}" alt="Inline"></body>').markdown
    assert f"![Inline]({src})" in md


# --- properties ------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(st.text())
def test_never_raises_on_arbitrary_text(text):
    result = page_to_markdown(text, URL)
    assert isinstance(result.markdown, str)
    assert isinstance(result.title, str)


@settings(max_examples=50, deadline=None)
@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200))
def test_markdown_always_starts_with_single_title_heading(text):
    result = page_to_markdown(f"<body><p>{text}</p></body>", URL)
    assert result.markdown.startswith("# ")


# --- chapter link mapping --------------------------------------------------

from web_to_epub.core.url_list import normalize_url  # noqa: E402

SITE_PAGE = "https://site/course/less1.htm"
LESS2_KEY = normalize_url("https://site/course/less2.htm")
FILES = {LESS2_KEY: "02-less2.md"}


def _link_page(href: str, text: str = "Next") -> str:
    return f'<body><p><a href="{href}">{text}</a></p></body>'


def _map_convert(html: str, files=None, url: str = SITE_PAGE) -> str:
    return page_to_markdown(html, url, chapter_files=files).markdown


def test_link_to_mapped_sibling_becomes_chapter_file_link():
    md = _map_convert(_link_page("less2.htm"), FILES)
    assert "[Next](02-less2.md)" in md
    assert "https://site/course/less2.htm" not in md


def test_fragment_dropped_on_mapped_link():
    md = _map_convert(_link_page("less2.htm#section-3"), FILES)
    assert "[Next](02-less2.md)" in md
    assert "#section-3" not in md


def test_link_to_unmapped_page_keeps_absolute_url():
    md = _map_convert(_link_page("other.htm"), FILES)
    assert "[Next](https://site/course/other.htm)" in md
    assert "02-less2.md" not in md


def test_link_to_self_keeps_absolute_url():
    files = {**FILES, normalize_url(SITE_PAGE): "01-less1.md"}
    md = _map_convert(_link_page("less1.htm"), files)
    assert "[Next](https://site/course/less1.htm)" in md
    assert "01-less1.md" not in md


def test_fragment_only_link_becomes_plain_text():
    md = _map_convert(_link_page("#top", "Back to top"), FILES)
    assert "Back to top" in md
    assert "](" not in md
    assert "#top" not in md


def test_url_form_equivalents_all_map():
    forms = [
        "less2.htm",
        "/course/less2.htm",
        "https://site/course/less2.htm",
        "https://site/course/less2.htm#x",
        "https://SITE/course/less2.htm",
        "https://site:443/course/less2.htm",
        "HTTPS://Site:443/course/less2.htm#frag",
    ]
    for href in forms:
        md = _map_convert(_link_page(href), FILES)
        assert "[Next](02-less2.md)" in md, href


def test_trailing_slash_root_form_maps():
    files = {normalize_url("https://site"): "00-home.md"}
    for href in ["https://site", "https://site/", "/"]:
        md = _map_convert(_link_page(href), files)
        assert "[Next](00-home.md)" in md, href


def test_mapped_link_honors_base_href():
    html = (
        '<html><head><base href="https://site/course/"></head>'
        '<body><a href="less2.htm">Go</a></body></html>'
    )
    md = _map_convert(html, FILES, "https://elsewhere/x.htm")
    assert "[Go](02-less2.md)" in md


def test_image_inside_mapped_link_keeps_image():
    html = '<body><a href="less2.htm"><img src="n.png" alt="Next pic"></a></body>'
    md = _map_convert(html, FILES)
    assert "![Next pic](https://site/course/n.png)" in md
    assert "(02-less2.md)" in md


def test_image_inside_unmapped_link_keeps_image_and_url():
    html = '<body><a href="other.htm"><img src="n.png" alt="Pic"></a></body>'
    md = _map_convert(html, FILES)
    assert "![Pic](https://site/course/n.png)" in md
    assert "(https://site/course/other.htm)" in md


def test_image_inside_fragment_only_link_keeps_image():
    html = '<body><a href="#top"><img src="n.png" alt="Pic"></a></body>'
    md = _map_convert(html, FILES)
    assert "![Pic](https://site/course/n.png)" in md
    assert "#top" not in md


def test_heading_ids_do_not_survive_in_mapped_links():
    html = '<body><h2 id="sec">Sec</h2><a href="less2.htm#sec">Jump</a></body>'
    md = _map_convert(html, FILES)
    assert "[Jump](02-less2.md)" in md
    assert "#sec" not in md


_HREFS = st.sampled_from(
    [
        "less2.htm",
        "less2.htm#a",
        "other.htm",
        "#top",
        "https://site/course/less2.htm",
        "mailto:a@b.com",
        "javascript:void(0)",
        "less1.htm",
        "https://other.org/x",
    ]
)
_LINK_TEXTS = st.text(alphabet="abcdefghij", min_size=1, max_size=6)


def _links_html(pairs) -> str:
    items = "".join(f'<p><a href="{h}">{t}</a></p>' for h, t in pairs)
    return f"<body>{items}</body>"


@settings(max_examples=50, deadline=None)
@given(st.lists(st.tuples(_HREFS, _LINK_TEXTS), max_size=8))
def test_empty_map_output_equals_default_output(pairs):
    html = _links_html(pairs)
    assert page_to_markdown(html, SITE_PAGE, chapter_files={}) == page_to_markdown(
        html, SITE_PAGE
    )


@settings(max_examples=50, deadline=None)
@given(
    # fragment-only links are excluded: they become plain text whenever a map is given
    st.lists(st.tuples(_HREFS.filter(lambda h: h != "#top"), _LINK_TEXTS), max_size=8),
    st.dictionaries(
        st.sampled_from(
            [
                LESS2_KEY,
                normalize_url("https://other.org/x"),
                normalize_url("https://site/course/other.htm"),
            ]
        ),
        st.sampled_from(["02-a.md", "03-b.md"]),
    ),
)
def test_map_changes_only_targets_not_link_texts(pairs, files):
    html = _links_html(pairs)
    with_map = page_to_markdown(html, SITE_PAGE, chapter_files=files).markdown
    without = page_to_markdown(html, SITE_PAGE).markdown
    link_re = re.compile(r"\[([^\]]*)\]\([^)]*\)")
    assert link_re.findall(with_map) == link_re.findall(without)


# --- extra <h1> elements are demoted ----------------------------------------


def _level1_lines(md: str) -> list[str]:
    """Lines starting with '# ' outside fenced code blocks."""
    out, in_fence = [], False
    for ln in md.splitlines():
        if ln.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and ln.startswith("# "):
            out.append(ln)
    return out


def test_second_h1_is_demoted_to_h2():
    html = "<body><h1>Title</h1><p>a</p><h1>Second</h1><p>b</p></body>"
    md = _convert(html).markdown
    assert md.startswith("# Title")
    assert _level1_lines(md) == ["# Title"]
    assert "## Second" in md


def test_three_h1s_only_first_stays_level_one():
    html = "<body><h1>One</h1><p>a</p><h1>Two</h1><p>b</p><h1>Three</h1></body>"
    md = _convert(html).markdown
    assert _level1_lines(md) == ["# One"]
    assert "## Two" in md and "## Three" in md


def test_h1s_nested_in_article_are_demoted():
    html = "<body><article><h1>Main</h1><p>a</p><section><h1>Inner</h1></section></article></body>"
    md = _convert(html).markdown
    assert md.startswith("# Main")
    assert _level1_lines(md) == ["# Main"]
    assert "## Inner" in md


def test_h1s_nested_in_main_are_demoted():
    html = "<body><main><h1>Main</h1><div><h1>Inner</h1></div></main></body>"
    md = _convert(html).markdown
    assert _level1_lines(md) == ["# Main"]
    assert "## Inner" in md


def test_hash_line_in_code_block_is_not_counted_or_altered():
    html = (
        "<body><h1>Title</h1><pre><code># a shell comment\necho hi</code></pre>"
        "<h1>Later</h1></body>"
    )
    md = _convert(html).markdown
    assert "# a shell comment" in md
    assert "## a shell comment" not in md
    assert _level1_lines(md) == ["# Title"]
    assert "## Later" in md


@settings(max_examples=25, deadline=None)
@given(st.lists(st.from_regex(r"[A-Za-z]{1,8}", fullmatch=True), min_size=1, max_size=6))
def test_exactly_one_level_one_heading_for_any_number_of_h1s(titles):
    html = "<body>" + "".join(f"<h1>{t}</h1><p>text</p>" for t in titles) + "</body>"
    md = _convert(html).markdown
    assert md.startswith("# ")
    assert len(_level1_lines(md)) == 1
    for t in titles[1:]:
        assert f"## {t}" in md
