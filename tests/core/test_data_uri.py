"""Tests for core.data_uri.decode_data_uri(uri, max_bytes=DEFAULT_MAX_BYTES) -> ImageData.

Raises ValueError with a human-readable reason for anything that is not a base64
data: URI of a packageable image type (PNG, JPEG, GIF, WebP) within the size cap.
"""
import base64

import pytest
from hypothesis import given, strategies as st

from web_to_epub.core.data_uri import decode_data_uri
from web_to_epub.core.epub_builder import ImageData


def uri(data: bytes, media_type: str = "image/png") -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode()}"


def test_decodes_base64_png():
    assert decode_data_uri(uri(b"\x89PNG-payload")) == ImageData(b"\x89PNG-payload", "image/png")


def test_media_type_is_normalised_and_parameters_ignored():
    assert decode_data_uri(uri(b"abc", "IMAGE/JPEG")).media_type == "image/jpeg"
    assert decode_data_uri("data:image/png;charset=utf-8;base64,YWJj").data == b"abc"


@given(st.binary(min_size=1, max_size=2048), st.sampled_from(["image/png", "image/jpeg", "image/gif", "image/webp"]))
def test_round_trips_any_payload(data, media_type):
    assert decode_data_uri(uri(data, media_type)) == ImageData(data, media_type)


@pytest.mark.parametrize(
    "bad",
    [
        "data:image/png,rawtext",
        "data:image/png;base64",
        "data:;base64,YWJj",
        "data:text/plain;base64,YWJj",
        "data:image/svg+xml;base64,YWJj",
        "data:image/png;base64,***not base64***",
        "data:image/png;base64,",
        "http://x.test/a.png",
        "",
    ],
)
def test_rejects_anything_else_with_a_reason(bad):
    with pytest.raises(ValueError, match=r"\S"):
        decode_data_uri(bad)


def test_decoded_size_over_cap_is_rejected():
    with pytest.raises(ValueError, match="(?i)large"):
        decode_data_uri(uri(b"x" * 100), max_bytes=99)
    assert decode_data_uri(uri(b"x" * 100), max_bytes=100).data == b"x" * 100
