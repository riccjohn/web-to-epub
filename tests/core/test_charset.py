from hypothesis import given, strategies as st

from web_to_epub.core.charset import decode_html

CAFE_1252 = "café".encode("windows-1252")
QUOTE_1252 = "“hi”".encode("windows-1252")
BODY_1252 = b"<p>" + CAFE_1252 + b" " + QUOTE_1252 + b"</p>"
EXPECTED = "<p>café “hi”</p>"


def test_header_charset_windows_1252():
    out = decode_html(BODY_1252, "text/html; charset=windows-1252")
    assert out == EXPECTED


def test_header_charset_is_case_and_quote_tolerant():
    out = decode_html(BODY_1252, 'text/html; Charset="Windows-1252"')
    assert out == EXPECTED


def test_meta_charset_windows_1252():
    data = b'<html><head><meta charset="windows-1252"></head><body>' + CAFE_1252 + b"</body></html>"
    out = decode_html(data, None)
    assert "café" in out


def test_meta_http_equiv_content_type():
    data = (
        b'<html><head><meta http-equiv="Content-Type" '
        b'content="text/html; charset=windows-1252"></head><body>'
        + CAFE_1252
        + QUOTE_1252
        + b"</body></html>"
    )
    out = decode_html(data, "text/html")
    assert "café" in out
    assert "“hi”" in out


def test_header_wins_over_meta():
    # Header says windows-1252, meta claims utf-8; header must win.
    data = b'<meta charset="utf-8">' + CAFE_1252
    out = decode_html(data, "text/html; charset=windows-1252")
    assert out.endswith("café")


def test_meta_beyond_4kib_is_ignored():
    data = b"<!--" + b"x" * 5000 + b'--><meta charset="windows-1252">' + CAFE_1252
    out = decode_html(data, None)
    assert "�" in out
    assert "café" not in out


def test_utf8_bom_is_honored_and_stripped():
    data = b"\xef\xbb\xbf" + "café".encode("utf-8")
    out = decode_html(data, None)
    assert out == "café"


def test_default_is_utf8():
    assert decode_html("café ☕".encode("utf-8"), None) == "café ☕"
    assert decode_html("café".encode("utf-8"), "text/html") == "café"


def test_unknown_charset_falls_back_to_utf8():
    out = decode_html("café".encode("utf-8"), "text/html; charset=nonsense-999")
    assert out == "café"


def test_undecodable_bytes_use_replacement():
    out = decode_html(b"caf\xe9", None)
    assert out == "caf�"


def test_invalid_bytes_for_declared_charset_do_not_raise():
    out = decode_html(b"caf\xe9\xff", "text/html; charset=utf-8")
    assert isinstance(out, str)
    assert out.startswith("caf")


@given(st.binary(), st.one_of(st.none(), st.text()))
def test_always_returns_str(data, header):
    assert isinstance(decode_html(data, header), str)
