"""Tests for core.data_uri.decode_data_uri(uri, max_bytes=DEFAULT_MAX_BYTES) -> ImageData.

Raises ValueError with a human-readable reason for anything that is not a base64
data: URI of a packageable image type (PNG, JPEG, GIF, WebP) within the size cap.
"""
import base64

import pytest
from hypothesis import given, strategies as st

from web_to_epub.core.data_uri import decode_data_uri
from web_to_epub.core.epub_builder import ImageData


MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif": b"GIF89a",
    "image/webp": b"RIFF\x00\x00\x00\x00WEBP",
}


def uri(data: bytes, media_type: str = "image/png") -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode()}"


def test_decodes_base64_png():
    png = MAGIC["image/png"] + b"payload"
    assert decode_data_uri(uri(png)) == ImageData(png, "image/png")


def test_media_type_is_normalised_and_parameters_ignored():
    jpg = MAGIC["image/jpeg"] + b"abc"
    assert decode_data_uri(uri(jpg, "IMAGE/JPEG")).media_type == "image/jpeg"
    png = MAGIC["image/png"]
    assert decode_data_uri(f"data:image/png;charset=utf-8;base64,{base64.b64encode(png).decode()}").data == png


@given(st.binary(min_size=1, max_size=2048), st.sampled_from(["image/png", "image/jpeg", "image/gif", "image/webp"]))
def test_round_trips_any_payload(data, media_type):
    data = MAGIC[media_type] + data
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
        "data:image/png;base64,YWJj",  # bytes are not a PNG
        "data:image/jpeg;base64," + base64.b64encode(MAGIC["image/png"]).decode(),  # wrong type
        "http://x.test/a.png",
        "",
    ],
)
def test_rejects_anything_else_with_a_reason(bad):
    with pytest.raises(ValueError, match=r"\S"):
        decode_data_uri(bad)


def test_decoded_size_over_cap_is_rejected():
    data = MAGIC["image/png"] + b"x" * 92
    with pytest.raises(ValueError, match="(?i)large"):
        decode_data_uri(uri(data), max_bytes=99)
    assert decode_data_uri(uri(data), max_bytes=100).data == data


@given(st.binary(min_size=1, max_size=256), st.booleans(), st.booleans(), st.booleans())
def test_tolerates_padding_wraps_percent_encoding_and_urlsafe(data, strip_pad, wrap, urlsafe):
    data = MAGIC["image/png"] + data
    payload = base64.b64encode(data).decode()
    if urlsafe:
        payload = payload.replace("+", "-").replace("/", "_")
    if strip_pad:
        payload = payload.rstrip("=")
    if wrap:
        payload = "\n".join(payload[i : i + 16] for i in range(0, len(payload), 16))
    assert decode_data_uri(f"data:image/png;base64,{payload}").data == data


def test_percent_encoded_padding_and_plus_are_accepted():
    data = MAGIC["image/png"] + b"\xfb\xff"
    payload = base64.b64encode(data).decode().replace("+", "%2B").replace("=", "%3D")
    assert decode_data_uri(f"data:image/png;base64,{payload}").data == data
