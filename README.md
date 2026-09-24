# web-to-epub

Turn a set of Markdown or text files into an EPUB, from a small local web UI.

## Setup

Requires Python 3.12 or newer.

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run

```
.venv/bin/flask --app web_to_epub.shell.app:create_app run
```

Open http://127.0.0.1:5000/. The server binds to localhost only.

## Usage

1. Drop `.md`, `.markdown` or `.txt` files on the dropzone, or click it to browse.
   Files are put in natural order (`Chapter 2` before `Chapter 10`, the same
   ordering the server uses). File names must be unique.
2. Reorder by dragging the handle, or with the up/down buttons (keyboard
   friendly). Use the remove button to drop a file, or "Sort naturally" to reset.
3. Fill in the title and author (required). Language, description, a suffix to
   strip from chapter titles, and a cover image are optional.
4. Press "Build EPUB". The file downloads when ready. Errors show inline. If some
   images could not be fetched, the UI shows how many; the server reports only a
   count, so check the image links in your source files.

The UI only talks to `POST /convert`. Fields: repeated `files`, `order` (JSON
list of every uploaded file name exactly once), `title`, `author`, and optional
`language`, `description`, `strip_suffix`, `cover`.

## Mapping from the Wenderweald scripts

The earlier workflow in `wenderweald_ebook` was `scripts/process_chapters.py`
(clean titles, download images, prepare markdown) followed by
`scripts/build_epub.sh` (Pandoc). Here that becomes one step:

| Wenderweald | web-to-epub |
| --- | --- |
| Chapter files in `individual_chapters/` | Files dropped on the page |
| Title cleanup in `process_chapters.py` | "Strip suffix" option plus first `#` heading as title |
| Image download and caching | Remote images fetched during conversion; failures counted as warnings |
| `metadata.yaml` | Title, author, language, description fields |
| Cover `Wenderweald.webp` | Cover image field |
| Pandoc build | Built in (ebooklib), no Pandoc needed |

## Tests

```
.venv/bin/python -m pytest
```

## Milestone 2

URL scraping: a new HTML source (for example
https://www.learntarot.com/lessintro.htm) that fetches pages and produces the
same `Chapter` objects. `Chapter` is source-agnostic, so the EPUB builder and the
UI's ordering and metadata flow stay unchanged.
