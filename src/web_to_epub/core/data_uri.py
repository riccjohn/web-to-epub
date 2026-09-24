"""Pure decoding of base64 `data:` image URIs into ImageData."""

import base64
import binascii
import re

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.core.image_policy import DEFAULT_MAX_BYTES, IMAGE_EXTENSIONS, media_type

_DATA_URI = re.compile(r"data:([^,]*),(.*)", re.DOTALL | re.IGNORECASE)


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
    if len(payload) * 3 // 4 > max_bytes + 3:  # cheap bound before decoding
        raise ValueError(f"image too large: > {max_bytes} bytes")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid base64 data") from None
    if not data:
        raise ValueError("data: URI has no content")
    if len(data) > max_bytes:
        raise ValueError(f"image too large: {len(data)} > {max_bytes} bytes")
    return ImageData(data, kind)
