import re
import xml.etree.ElementTree as ET
from pathlib import Path

from hypothesis import given, settings, strategies as st

from web_to_epub.core.markdown_chapter import parse_chapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _xml(body: str) -> ET.Element:
    return ET.fromstring(f"<div xmlns:x='x'>{body}</div>")


def _count_img(body: str) -> int:
    return len(_xml(body).findall(".//img"))


# TITLE

def test_first_h1_is_title():
    ch = parse_chapter("# Hello World\n\nText.", "a.md")
    assert ch.title == "Hello World"


def test_strip_suffix_removed_from_title_and_heading():
    ch = parse_chapter("# Bloody Portents - Odinson Games\n\nText.", "a.md", strip_suffix=" - Odinson Games")
    assert ch.title == "Bloody Portents"
    assert "Odinson" not in ch.body
    assert "Bloody Portents" in ch.body


def test_no_h1_falls_back_to_filename_stem():
    ch = parse_chapter("Just text, no heading.", "Chapter 02 - Homecoming.md")
    assert ch.title == "Chapter 02 - Homecoming"


# TITLE vs CODE BLOCKS

def _h1s(body: str) -> list[str]:
    return ["".join(h.itertext()) for h in _xml(body).findall(".//h1")]


def test_h1_inside_backtick_fence_is_not_title():
    text = "Intro\n\n```bash\n# install deps\npip install x\n```\n\n# Real Title\n\nText."
    ch = parse_chapter(text, "a.md")
    assert ch.title == "Real Title"
    assert _h1s(ch.body) == ["Real Title"]
    assert "# install deps" in ch.body
    assert "pip install x" in ch.body


def test_h1_inside_tilde_fence_is_not_title():
    text = "~~~\n# tilde comment\n~~~\n\n# Real Title\n\nText."
    ch = parse_chapter(text, "a.md")
    assert ch.title == "Real Title"
    assert _h1s(ch.body) == ["Real Title"]
    assert "# tilde comment" in ch.body


def test_strip_suffix_does_not_alter_fenced_code():
    text = "```\n# something - Suffix\n```\n\n# Real - Suffix\n\nText."
    ch = parse_chapter(text, "a.md", strip_suffix=" - Suffix")
    assert ch.title == "Real"
    assert _h1s(ch.body) == ["Real"]
    assert "# something - Suffix" in ch.body


def test_only_h1_in_backtick_fence_falls_back_to_filename():
    text = "```\n# only comment\n```\n\nText."
    ch = parse_chapter(text, "My Chapter.md")
    assert ch.title == "My Chapter"
    assert _h1s(ch.body) == []
    assert "# only comment" in ch.body


def test_only_h1_in_tilde_fence_falls_back_to_filename():
    text = "~~~\n# tilde comment\n~~~\n"
    ch = parse_chapter(text, "My Chapter.md")
    assert ch.title == "My Chapter"
    assert _h1s(ch.body) == []
    assert "# tilde comment" in ch.body


# Regression guards: already correct today (markdown itself treats these as code).

def test_h1_inside_indented_code_is_not_title():
    text = "Para\n\n    # indented comment\n    x = 1\n\n# Real Title\n"
    ch = parse_chapter(text, "a.md")
    assert ch.title == "Real Title"
    assert _h1s(ch.body) == ["Real Title"]
    assert "# indented comment" in ch.body


def test_only_h1_in_indented_code_falls_back_to_filename():
    text = "Para\n\n    # indented comment\n    x = 1\n"
    ch = parse_chapter(text, "My Chapter.md")
    assert ch.title == "My Chapter"
    assert "# indented comment" in ch.body


# IMAGES

def test_titled_image_becomes_figure_with_caption():
    ch = parse_chapter('![A cat](http://x.test/cat.png "Cat caption")', "a.md")
    root = _xml(ch.body)
    fig = root.find(".//figure")
    assert fig is not None
    assert fig.find("img").get("src") == "http://x.test/cat.png"
    assert fig.find("figcaption").text == "Cat caption"
    assert ch.images[0].caption == "Cat caption"
    assert ch.images[0].alt == "A cat"


def test_untitled_image_is_plain_img():
    ch = parse_chapter("![A cat](http://x.test/cat.png)", "a.md")
    assert "<figure" not in ch.body
    assert _count_img(ch.body) == 1
    assert ch.images[0].caption is None


def test_images_collected_in_document_order():
    ch = parse_chapter("![a](http://x/1.png)\n\n![b](http://x/2.png)\n\n![c](http://x/3.png)", "a.md")
    assert [i.src for i in ch.images] == ["http://x/1.png", "http://x/2.png", "http://x/3.png"]
    assert all(i.is_remote for i in ch.images)


def test_substack_linked_image_has_no_wrapping_link():
    text = "[![alt](http://x/i.jpg \"cap\")\n\n](http://x/big.jpg)"
    ch = parse_chapter(text, "a.md")
    assert "<a" not in ch.body
    assert [i.src for i in ch.images] == ["http://x/i.jpg"]


def test_substack_fixture():
    text = (FIXTURES / "substack_chapter.md").read_text()
    ch = parse_chapter(text, "Chapter 01.md", strip_suffix=" - Odinson Games")
    assert ch.title == "Chapter 01 - Bloody Portents"
    assert len(ch.images) == 2
    assert "<a" not in ch.body
    assert "<figure" in ch.body
    assert ch.images[0].caption.startswith("Comic illustration")
    assert ch.images[1].caption is None
    assert _count_img(ch.body) == 2


def test_data_uri_and_relative_paths_not_remote():
    ch = parse_chapter("![a](data:image/png;base64,AAAA)\n\n![b](images/pic.png)", "a.md")
    assert [i.is_remote for i in ch.images] == [False, False]
    assert ch.images[1].src == "images/pic.png"


# SAFETY

def test_script_tag_removed():
    ch = parse_chapter("Hi\n\n<script>alert(1)</script>\n\nBye", "a.md")
    assert "<script" not in ch.body
    assert "alert(1)" not in ch.body


def test_event_handler_attributes_removed():
    ch = parse_chapter('<img src="http://x/a.png" onerror="alert(1)">', "a.md")
    assert "onerror" not in ch.body
    assert "alert" not in ch.body


# PROPERTIES

@settings(max_examples=100, deadline=None)
@given(st.text(max_size=300))
def test_output_always_parses_as_xml(text):
    ch = parse_chapter(text, "f.md")
    _xml(ch.body)


@settings(max_examples=100, deadline=None)
@given(st.lists(st.sampled_from(["![a](http://x/a.png)", '![b](http://x/b.png "cap")',
                                 "[![c](http://x/c.png)](http://x/l)", "![d](rel/d.png)",
                                 "text & <b>bold</b>", "# H"]), max_size=8))
def test_image_ref_count_equals_img_tags(parts):
    ch = parse_chapter("\n\n".join(parts), "f.md")
    assert len(ch.images) == _count_img(ch.body)


# REVIEW FIXES

def test_col_and_wbr_void_tags_are_self_closed():
    ch = parse_chapter("<table><colgroup><col></colgroup><tr><td>a</td></tr></table>\n\nlong<wbr>word", "a.md")
    _xml(ch.body)
    assert "<col/>" in ch.body and "<wbr/>" in ch.body


def test_colspan_rowspan_and_ol_start_survive():
    ch = parse_chapter('<table><tr><td colspan="2" rowspan="3">a</td></tr></table>\n\n<ol start="5"><li>x</li></ol>', "a.md")
    _xml(ch.body)
    assert 'colspan="2"' in ch.body and 'rowspan="3"' in ch.body
    assert '<ol start="5">' in ch.body


def test_attribute_values_are_escaped():
    ch = parse_chapter('<ol start="5&quot; onclick=&quot;x"><li>x</li></ol>', "a.md")
    root = _xml(ch.body)
    assert "onclick" not in root.find(".//ol").attrib


def test_title_that_is_only_the_suffix_falls_back_to_filename():
    ch = parse_chapter("# Site Name\n\nText.", "Chapter 3.md", strip_suffix="Site Name")
    assert ch.title == "Chapter 3"


def test_title_is_trimmed_after_suffix_removal():
    ch = parse_chapter("# Hello | Site\n\nText.", "a.md", strip_suffix="| Site")
    assert ch.title == "Hello"
