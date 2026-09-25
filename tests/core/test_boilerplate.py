from hypothesis import given, strategies as st

from web_to_epub.core.boilerplate import strip_shared_blocks

NAV = "[Home](https://s/top) | [About](https://s/about)"
FOOTER = "Copyright 2021 Someone"


def _page(n, extra=""):
    return f"# Page {n}\n\nUnique body {n}.\n\n{extra}{NAV}\n\n---\n\n{FOOTER}"


def test_blocks_shared_by_most_pages_are_removed_and_content_kept():
    out = strip_shared_blocks([_page(i) for i in range(4)])
    for i, md in enumerate(out):
        assert md == f"# Page {i}\n\nUnique body {i}."


def test_fewer_than_three_pages_are_left_alone():
    pages = [_page(1), _page(2)]
    assert strip_shared_blocks(pages) == pages


def test_block_in_only_a_minority_of_pages_is_kept():
    pages = [_page(i) for i in range(5)]
    pages[0] += "\n\nSpecial note"
    pages[1] += "\n\nSpecial note"
    assert "Special note" in strip_shared_blocks(pages)[0]


def test_repeated_headings_are_kept():
    pages = [f"# P{i}\n\n## References\n\nbody {i}" for i in range(4)]
    assert strip_shared_blocks(pages) == pages


def test_titles_are_never_removed_even_if_identical():
    pages = ["# Same\n\nbody a", "# Same\n\nbody b", "# Same\n\nbody c"]
    assert all(md.startswith("# Same") for md in strip_shared_blocks(pages))


def test_blank_lines_inside_code_fences_do_not_split_blocks():
    code = "```\na\n\nb\n```"
    pages = [f"# P{i}\n\nbody {i}\n\n{code}\n\ntail {i}" for i in range(4)]
    assert all(code not in md for md in strip_shared_blocks(pages))


def test_links_to_any_chapter_compare_equal():
    is_chapter = lambda t: t.endswith(".md")
    same = [f"# P{i}\n\nbody {i}\n\n[Prev](p{i}.md)" for i in range(4)]
    assert all("Prev" not in md for md in strip_shared_blocks(same, is_chapter))
    assert strip_shared_blocks(same) == same  # without the hint the targets differ


@given(st.lists(st.text(alphabet="abc \n#-", max_size=40), max_size=6))
def test_never_raises_and_keeps_titles(pages):
    docs = [f"# T\n\n{p}" for p in pages]
    out = strip_shared_blocks(docs)
    assert len(out) == len(docs)
    assert all(md.startswith("# T") for md in out)
