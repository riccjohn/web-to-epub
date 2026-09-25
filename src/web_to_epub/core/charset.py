import re

_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([^\s\"';]+)", re.IGNORECASE)
_META_CHARSET = re.compile(
    rb"<meta[^>]*?charset\s*=\s*[\"']?([^\s\"';>/]+)", re.IGNORECASE
)
_BOM = b"\xef\xbb\xbf"
_SNIFF_BYTES = 4096


def decode_html(data: bytes, content_type_header: str | None) -> str:
    if data.startswith(_BOM):
        return data[len(_BOM):].decode("utf-8", errors="replace")

    name = None
    if content_type_header:
        match = _HEADER_CHARSET.search(content_type_header)
        if match:
            name = match.group(1)
    if name is None:
        meta = _META_CHARSET.search(data[:_SNIFF_BYTES])
        if meta:
            name = meta.group(1).decode("ascii", errors="replace")

    if name:
        try:
            return data.decode(name, errors="replace")
        except (LookupError, ValueError, TypeError):
            pass
    return data.decode("utf-8", errors="replace")
