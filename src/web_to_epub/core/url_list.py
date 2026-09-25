"""URL list cleaning, normalization, and chapter filename derivation."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class UrlError:
    entry: str
    reason: str


@dataclass(frozen=True)
class UrlListResult:
    urls: list[str] = field(default_factory=list)
    errors: list[UrlError] = field(default_factory=list)


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError(f"unsupported scheme: {parts.scheme!r} (need http or https)")
    host = parts.hostname
    if not host:
        raise ValueError("missing host")
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    netloc = host if port is None or port == _DEFAULT_PORTS[scheme] else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def chapter_filename(index: int, url: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:50].strip("-")
    return f"{index:03d}-{slug or 'chapter'}.md"


def clean_url_list(entries: list[str], max_count: int = 50) -> UrlListResult:
    stripped = [e.strip() for e in entries]
    stripped = [e for e in stripped if e]
    if len(stripped) > max_count:
        raise ValueError(f"too many URLs: {len(stripped)} (max {max_count})")
    urls: list[str] = []
    errors: list[UrlError] = []
    seen: set[str] = set()
    for entry in stripped:
        try:
            normalized = normalize_url(entry)
        except ValueError as exc:
            errors.append(UrlError(entry, str(exc)))
            continue
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return UrlListResult(urls=urls, errors=errors)
