import re

import pytest
from hypothesis import given, strategies as st

from web_to_epub.core.url_list import (
    chapter_filename,
    clean_url_list,
    normalize_url,
)

# Interface under test for clean_url_list(entries, max_count):
#   returns an object with `.urls` (list[str], accepted, deduped, first-seen
#   order) and `.errors` (list of objects with `.entry` and non-empty
#   `.reason`). More than max_count non-blank entries raises ValueError.

hosts = st.from_regex(r"[a-z][a-z0-9]{0,8}(\.[a-z][a-z0-9]{0,8}){1,2}", fullmatch=True)
paths = st.from_regex(r"(/[A-Za-z0-9_.~-]{1,8}){0,3}/?", fullmatch=True)
queries = st.one_of(st.just(""), st.from_regex(r"\?[a-z]{1,4}=[a-z0-9]{1,4}", fullmatch=True))
fragments = st.one_of(st.just(""), st.from_regex(r"#[a-z0-9]{1,6}", fullmatch=True))
schemes = st.sampled_from(["http", "https", "HTTP", "HTTPS", "Http"])
urls = st.builds(
    lambda s, h, p, q, f: f"{s}://{h}{p}{q}{f}", schemes, hosts, paths, queries, fragments
)


# --- normalize_url ---------------------------------------------------------


@given(urls)
def test_normalize_is_idempotent(url):
    once = normalize_url(url)
    assert normalize_url(once) == once


@given(urls)
def test_normalize_never_returns_fragment(url):
    assert "#" not in normalize_url(url)


def test_normalize_lowercases_host_and_drops_default_port_and_fragment():
    assert normalize_url("HTTP://Example.com:80/a#x") == "http://example.com/a"


@pytest.mark.parametrize(
    "a, b",
    [
        ("http://example.com/a", "http://example.com/a#section"),
        ("http://example.com/a#one", "http://example.com/a#two"),
        ("http://EXAMPLE.com/a", "http://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com", "http://example.com/"),
        ("https://example.com/a?x=1#f", "https://example.com/a?x=1"),
    ],
)
def test_equivalent_urls_normalize_equal(a, b):
    assert normalize_url(a) == normalize_url(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("http://example.com/a", "http://example.com/b"),
        ("http://example.com/a?x=1", "http://example.com/a?x=2"),
        ("http://example.com/a", "http://example.com/a?x=1"),
        ("http://example.com/a", "https://example.com/a"),
        ("http://example.com:8080/a", "http://example.com/a"),
        ("http://example.com/a", "http://example.com/a/"),
    ],
)
def test_distinct_urls_normalize_differently(a, b):
    assert normalize_url(a) != normalize_url(b)


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.com/a",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "mailto:a@b.com",
        "http://",
        "https:///path",
        "example.com/a",
        "/relative/path",
        "",
    ],
)
def test_normalize_rejects_non_http_or_hostless(bad):
    with pytest.raises(ValueError):
        normalize_url(bad)


# --- chapter_filename ------------------------------------------------------


@given(st.integers(min_value=0, max_value=999), st.text())
def test_chapter_filename_is_safe_for_arbitrary_url_text(index, url):
    name = chapter_filename(index, url)
    assert name.endswith(".md")
    assert "/" not in name and "\\" not in name
    assert ".." not in name
    assert not re.search(r"[\x00-\x1f\x7f]", name)
    assert name not in ("", ".md")


@given(
    st.lists(st.integers(min_value=0, max_value=999), min_size=2, max_size=20, unique=True),
    urls,
)
def test_chapter_filename_sorts_in_index_order(indexes, url):
    names = {i: chapter_filename(i, url) for i in indexes}
    by_name = sorted(indexes, key=lambda i: names[i])
    assert by_name == sorted(indexes)


def test_chapter_filename_two_sorts_before_ten():
    assert chapter_filename(2, "http://a.com/x") < chapter_filename(10, "http://a.com/x")


@given(
    st.integers(min_value=0, max_value=999),
    st.integers(min_value=0, max_value=999),
    st.text(),
)
def test_distinct_indexes_give_distinct_names_for_identical_urls(i, j, url):
    if i != j:
        assert chapter_filename(i, url) != chapter_filename(j, url)


def test_chapter_filename_neutralises_traversal_in_url():
    name = chapter_filename(1, "http://x.com/../../etc/passwd\x00\n")
    assert name.endswith(".md")
    assert "/" not in name and ".." not in name
    assert not re.search(r"[\x00-\x1f\x7f]", name)


# --- clean_url_list --------------------------------------------------------


def test_clean_trims_whitespace_and_drops_blanks():
    result = clean_url_list(["  http://a.com/x  ", "", "   ", "\t\n", "http://b.com/y"])
    assert [normalize_url(u) for u in result.urls] == [
        "http://a.com/x",
        "http://b.com/y",
    ]
    assert result.errors == []


def test_clean_dedupes_on_normalized_form_keeping_first_order():
    result = clean_url_list(
        [
            "http://b.com/y",
            "http://A.com/x#top",
            "HTTP://a.com:80/x",
            "http://b.com/y#z",
            "http://c.com",
            "http://c.com/",
        ]
    )
    assert [normalize_url(u) for u in result.urls] == [
        "http://b.com/y",
        "http://a.com/x",
        "http://c.com/",
    ]
    assert result.errors == []


def test_clean_rejects_invalid_entries_with_reason_and_keeps_valid():
    result = clean_url_list(["http://a.com/x", "ftp://a.com/f", "not a url", "https://b.com"])
    assert [normalize_url(u) for u in result.urls] == [
        "http://a.com/x",
        "https://b.com/",
    ]
    assert [e.entry for e in result.errors] == ["ftp://a.com/f", "not a url"]
    assert all(isinstance(e.reason, str) and e.reason.strip() for e in result.errors)


def test_clean_enforces_max_count():
    entries = [f"http://a.com/{i}" for i in range(4)]
    assert len(clean_url_list(entries, max_count=4).urls) == 4
    with pytest.raises(ValueError):
        clean_url_list(entries, max_count=3)


def test_clean_max_count_ignores_blank_entries():
    entries = ["http://a.com/1", "", "  ", "http://a.com/2"]
    assert len(clean_url_list(entries, max_count=2).urls) == 2


@given(st.lists(urls, max_size=10))
def test_clean_output_has_no_duplicates_and_is_idempotent(entries):
    result = clean_url_list(entries, max_count=50)
    normalized = [normalize_url(u) for u in result.urls]
    assert len(normalized) == len(set(normalized))
    again = clean_url_list(result.urls, max_count=50)
    assert [normalize_url(u) for u in again.urls] == normalized


# --- credentials are stripped (security-motivated characterization) ----------
# Userinfo (user:pass@) must never survive normalization: otherwise it would
# leak into the Host header of outgoing requests and into the stored chapter URL.


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://user:pass@Example.com/a", "https://example.com/a"),
        ("http://u:p@host:8080/x", "http://host:8080/x"),
        ("https://onlyuser@example.com/", "https://example.com/"),
    ],
)
def test_normalize_url_drops_userinfo(raw, expected):
    assert normalize_url(raw) == expected


def test_clean_url_list_never_returns_credentials():
    res = clean_url_list(["https://user:secret@example.com/a", "http://u:p@host:8080/x"])
    assert res.urls
    assert all("@" not in u and "secret" not in u for u in res.urls)


def test_clean_url_list_dedupes_entries_differing_only_by_credentials():
    res = clean_url_list(
        ["https://a:b@example.com/p", "https://c:d@example.com/p", "https://example.com/p"]
    )
    assert res.urls == ["https://example.com/p"]


def test_chapter_filenames_differ_for_urls_sharing_a_long_prefix():
    prefix = "https://example.com/" + "a" * 60
    assert chapter_filename(0, prefix + "/one") != chapter_filename(0, prefix + "/two")
