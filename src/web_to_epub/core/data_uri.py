"""Pure decoding of base64 `data:` image URIs into ImageData."""

import base64
import binascii
import re
from urllib.parse import unquote

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.core.image_policy import DEFAULT_MAX_BYTES, IMAGE_EXTENSIONS, matches_signature, media_type

_DATA_URI = re.compile(r"data:([^,]*),(.*)", re.DOTALL | re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class ImageTooLarge(ValueError):
    """The decoded image would exceed the byte cap."""


def _normalise_base64(payload: str) -> str:
    """Accept percent-encoding, line wraps, URL-safe alphabet and missing padding."""
    text = _WHITESPACE.sub("", unquote(payload)).translate(str.maketrans("-_", "+/")).rstrip("=")
    return text + "=" * (-len(text) % 4)


def decode_data_uri(uri: str, max_bytes: int = DEFAULT_MAX_BYTES) -> ImageData:
    """Raise ValueError (with a readable reason) unless `uri` is a base64 image of a packageable type."""
    match = _DATA_URI.fullmatch(uri)
    if match is None:
        raise ValueError("not a data: URI")
    header, payload = match.groups()
    parts = [part.strip().lower() for part in header.split(";")]
    if "base64" not in parts[1:]:
        raise ValueError("only base64 data: URIs are supported")
    kind = media_type(parts[0])
    if kind not in IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image content type: {kind!r}")
    normalised = _normalise_base64(payload)
    if len(normalised) * 3 // 4 > max_bytes + 3:  # cheap bound before decoding
        raise ImageTooLarge(f"image too large: > {max_bytes} bytes")
    try:
        data = base64.b64decode(normalised, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid base64 data") from None
    if not data:
        raise ValueError("data: URI has no content")
    if len(data) > max_bytes:
        raise ImageTooLarge(f"image too large: {len(data)} > {max_bytes} bytes")
    if not matches_signature(data, kind):
        raise ValueError(f"data does not look like {kind}")
    return ImageData(data, kind)
