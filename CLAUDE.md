# web-to-epub

Converts content into EPUB files. Python 3.14 works (ebooklib imports fine); requires Python >= 3.12.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Runtime deps: flask, ebooklib, markdown, nh3, beautifulsoup4, html5lib, markdownify. Dev deps: pytest, hypothesis.

## Tests

```
.venv/bin/python -m pytest
```

## Architecture

src layout, package `web_to_epub`.

- `src/web_to_epub/core/`: pure logic. No I/O, no flask, no network. Must never import `shell` or `flask`.
- `src/web_to_epub/shell/`: all I/O (flask app, filesystem, network, EPUB writing).

`Chapter` must stay source-agnostic. A URL/HTML source is planned for milestone 2, so do not bake in assumptions about where chapter content comes from.

## Test rules

- Test at boundaries (public interfaces of core and shell), not internals.
- No mocking of internal modules. Use real objects; fake only true external edges.
- Use hypothesis for property-based tests where properties exist.
- Mirror layout: `tests/core/`, `tests/shell/`.

## Misc

`.gitignore` must keep the `.yaks` line (yaks breaks without it).
