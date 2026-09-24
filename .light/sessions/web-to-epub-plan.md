# web-to-epub - Implementation Plan

**Date:** 2026-09-23
**Status:** Plan - Ready for Review
**Tracker:** yaks
**Yaks Epic:** web-to-epub-v1

## Context

`../wenderweald_ebook` converts Substack markdown exports to EPUB with two scripts: `process_chapters.py` (strip title suffix, download and cache remote images, unwrap linked images, wrap captioned images in `<figure>`) and `build_epub.sh` (Pandoc `--to=epub3`, metadata YAML, TOC, cover, CSS). Both are hardcoded to that book (paths, `Chapter *.md` glob, "- Odinson Games" suffix, a caption heuristic that guesses).

The ultimate goal is to also turn a website's lessons into an EPUB, one chapter per lesson, starting with `https://www.learntarot.com/lessintro.htm` (static HTML 4; index lists `less1.htm`..`less19.htm` plus `lessp.htm`; shared footer to strip; content (c) Joan Bunning, personal use). **That is milestone 2.** v1 is the markdown upload site, but the core is designed so a URL source can plug in without rework.

**Decisions made with the user:**
- Python + Flask + **ebooklib** (no Pandoc dependency).
- **Personal/local tool first**; hosting later.
- **Markdown upload first**; URL scraping is milestone 2.
- Chapter order: **natural filename sort + drag to reorder**.
- Stateless: upload, convert, download; nothing persisted.

**Design consequences of those decisions:**
- With ebooklib we own markdown-to-XHTML, the TOC and packaging. Use the `markdown` package for md-to-HTML and ebooklib for EPUB assembly.
- The core works on a source-agnostic `Chapter` (title, XHTML body, image refs), so a future HTML-scraping source produces the same `Chapter`s.
- Substack-specific behavior is dropped or made generic: title-suffix stripping becomes an optional user field; the caption heuristic is replaced by the markdown image title (`![alt](url "caption")`) becoming a `<figcaption>`; linked-image unwrapping is kept (generic).
- Remote images are still fetched (Wenderweald needs it), but with SSRF and size guards and TLS verification on. The old script disabled it.

## Goal

A local web app where the user drags markdown files in, reorders them, fills in title/author (and optionally a cover), and downloads a valid EPUB with one chapter per file, a TOC, and embedded images. The conversion core is a plain Python library that later milestones (CLI, URL scraping) reuse.

## Acceptance Criteria

- [ ] Dropping N markdown files produces an EPUB with N chapters in the displayed order; the TOC lists each chapter title.
- [ ] Filenames sort naturally (`Chapter 2` before `Chapter 10`); dragging changes the order used in the build.
- [ ] Chapter title comes from the first H1 (with optional suffix stripped), falling back to the filename.
- [ ] Remote images are downloaded and embedded; a failed or blocked image degrades to no image with a warning, never a failed build.
- [ ] Image fetching refuses non-http(s) URLs, private/loopback/link-local targets, oversized responses and slow responses.
- [ ] Images with a markdown title render as `<figure>` with `<figcaption>`; linked images are unwrapped to plain images.
- [ ] Optional cover image upload becomes the EPUB cover.
- [ ] EPUB reads back cleanly with ebooklib (spine order, TOC, metadata, image items) and opens in an EPUB reader.
- [ ] Bad input (no files, non-UTF-8, non-markdown, oversized) returns a clear 4xx error message shown in the UI.
- [ ] Nothing is written to disk that outlives the request.
- [ ] Converting the real Wenderweald chapters works as a manual smoke test.

## Files to Create

### Core (`src/web_to_epub/core/`)
- `models.py` - `Chapter`, `ImageRef`, `BookMetadata` dataclasses (source-agnostic).
- `ordering.py` - natural filename sort.
- `markdown_chapter.py` - markdown text to `Chapter` (title extraction, XHTML, image collection, caption/linked-image handling, raw-HTML sanitization).
- `image_policy.py` - pure URL/size policy: scheme check, private-address check, size and content-type limits.
- `epub_builder.py` - `Chapter`s + metadata + images + optional cover to EPUB bytes via ebooklib.
- `styles.py` - default EPUB stylesheet (ported and trimmed from the Wenderweald CSS).

### Shell (`src/web_to_epub/shell/`)
- `image_fetcher.py` - performs the download using `image_policy` (redirect re-validation, timeouts, byte cap).
- `convert.py` - use case: uploaded files + options to EPUB bytes plus warnings.
- `app.py` - Flask app factory and routes.
- `static/index.html`, `static/app.js`, `static/app.css` - drag-and-drop UI.

### Tests
- `tests/core/test_ordering.py`, `test_markdown_chapter.py`, `test_image_policy.py`, `test_epub_builder.py`
- `tests/shell/test_image_fetcher.py` (real local HTTP server), `test_convert.py`, `test_app.py`
- `tests/fixtures/` - small sample chapters (with/without images, captions, linked images).

### Project
- `pyproject.toml`, `CLAUDE.md`, `README.md`, `.gitignore`

## Files to Modify

None (greenfield). `git init` in Phase 0.

## Implementation Phases

### Phase 0: Project Scaffold
**Goal:** Working Python project with a passing empty test run.

**Tasks:**
1. `git init`, `.gitignore` (`.venv`, `__pycache__`, `.light/` stays tracked).
2. `pyproject.toml`: package `web_to_epub` (src layout), deps `flask`, `ebooklib`, `markdown`, `nh3`; dev deps `pytest`, `hypothesis`.
3. Create `.venv`, install, confirm ebooklib imports on Python 3.14 (fall back to a 3.12/3.13 interpreter if not, and record it in CLAUDE.md).
4. `CLAUDE.md` with setup, test command, architecture (core = pure, shell = I/O), and "no internal mocks".

**Verification:**
- [ ] `python -m pytest` runs (0 tests collected is fine) and exits 0
- [ ] `python -c "import ebooklib, markdown, flask, nh3"` succeeds

#### Agent Context
- **Files to create/modify:** `pyproject.toml`, `.gitignore`, `CLAUDE.md`, `src/web_to_epub/__init__.py`, `src/web_to_epub/core/__init__.py`, `src/web_to_epub/shell/__init__.py`, `tests/__init__.py`
- **Commands to run:** `git init`; `python3 -m venv .venv`; `.venv/bin/pip install -e ".[dev]"`; `.venv/bin/python -m pytest`
- **Acceptance gate:** Deps import; pytest exits 0 (no tests is acceptable)
- **Architectural constraints:** src layout; `core` must not import `shell`, `flask` or do any I/O

---

### Phase 1: Chapter Ordering (L3 Core)
**Goal:** Sort filenames the way a human expects.

**Test Spec (Behavioral):**
- Properties: the result is a permutation of the input (nothing lost or duplicated); sorting is idempotent; order is independent of input order.
- Examples of intent: `Chapter 2` sorts before `Chapter 10`; zero-padded and unpadded numbers interleave by value; sorting is case-insensitive; names without digits fall back to alphabetical.

**Tasks:** write tests (RED), verify failure, implement `natural_sort(names)` (GREEN).

**Verification:**
- [ ] Property tests pass; natural-order examples pass

#### Agent Context
- **Files to create:** `tests/core/test_ordering.py`, `src/web_to_epub/core/ordering.py`
- **Test spec:** see above
- **Test command:** `.venv/bin/python -m pytest tests/core/test_ordering.py`
- **RED gate:** Tests fail on import of `natural_sort` from a not-yet-existing module is a **wrong-reason** RED; create a stub returning input unchanged first so the assertion "Chapter 2 sorts before Chapter 10" is what fails
- **GREEN gate:** All ordering tests pass
- **Architectural constraints:** Pure function, no I/O

---

### Phase 2: Markdown to Chapter (L3 Core)
**Goal:** Turn one markdown document into a `Chapter` (title, XHTML body, image refs).

**Test Spec (Behavioral):**
- Title: first H1 text becomes the title; with an optional `strip_suffix` (for example `" - Odinson Games"`) it is removed from the title and the rendered heading; no H1 falls back to the filename stem without extension.
- Images: every image reference is collected in document order; `![alt](url "caption")` renders as `<figure><img><figcaption>caption</figcaption></figure>`; an image without a title renders as a plain `<img>`; the Substack pattern `[![alt](img)](link)` renders as a plain image with no wrapping link; data URIs and local relative paths are collected but flagged as non-remote.
- Safety: `<script>` and event-handler attributes in raw HTML are removed; output is well-formed XHTML (parses as XML).
- Invariants (property tests): output always parses as XML for arbitrary markdown text; the number of collected image refs equals the number of `<img>` tags in the output.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Tests pass; XML well-formedness property holds

#### Agent Context
- **Files to create:** `tests/core/test_markdown_chapter.py`, `tests/fixtures/*.md`, `src/web_to_epub/core/models.py`, `src/web_to_epub/core/markdown_chapter.py`
- **Test spec:** see above
- **Test command:** `.venv/bin/python -m pytest tests/core/test_markdown_chapter.py`
- **RED gate:** Assertion failures on title/figure/image-count behavior against a stub `parse_chapter` returning an empty `Chapter`; an ImportError or setup error is a wrong-reason RED
- **GREEN gate:** All tests pass
- **Architectural constraints:** Pure; uses `markdown` and `nh3` only; the `Chapter` model must not mention markdown so an HTML source can produce it later

---

### Phase 3: Image Policy (L3 Core)
**Goal:** Decide what is safe to fetch, as a pure function.

**Test Spec (Behavioral):**
- Rejects: non-http(s) schemes (`file:`, `ftp:`, `data:`), URLs with credentials, hosts resolving to loopback, private (RFC1918), link-local (including `169.254.169.254`), unspecified and IPv6 equivalents, and IPv4-mapped IPv6 forms.
- Accepts: ordinary public http(s) image URLs.
- Size/content-type policy: responses over the byte cap or with a non-`image/*` type are rejected; the cap is configurable.
- Invariant: for any IP address in a private/reserved range (generated), the policy rejects it.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Policy tests and property tests pass

#### Agent Context
- **Files to create:** `tests/core/test_image_policy.py`, `src/web_to_epub/core/image_policy.py`
- **Test spec:** see above (take already-resolved IP addresses as input so the core does no DNS)
- **Test command:** `.venv/bin/python -m pytest tests/core/test_image_policy.py`
- **RED gate:** Assertion failures where a stub policy accepts everything (for example the metadata-IP URL is accepted when it should be rejected); import errors are wrong-reason
- **GREEN gate:** All tests pass
- **Architectural constraints:** Pure; stdlib `ipaddress` and `urllib.parse` only; no sockets

---

### Phase 4: EPUB Builder (L3 Core)
**Goal:** Assemble a valid EPUB from chapters, metadata, image bytes and an optional cover.

**Test Spec (Behavioral):**
- Building N chapters and reading the result back with ebooklib yields N content documents in spine order, a TOC with N entries in the same order and with the chapter titles, and the supplied title, author, language and description in the metadata.
- Every image referenced by a chapter is present in the package and the XHTML `src` points at it; an image with no bytes (failed fetch) is dropped from the chapter without breaking the build.
- A cover, when supplied, is registered as the cover image; absent cover is fine.
- The stylesheet is included and linked from every chapter.
- The output is a zip whose first entry is `mimetype` (uncompressed) with the EPUB media type.
- Invariants: chapter order in the output equals input order; building the same input twice gives the same chapters, TOC and metadata; zero chapters is rejected with a clear error.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Round-trip tests pass

#### Agent Context
- **Files to create:** `tests/core/test_epub_builder.py`, `src/web_to_epub/core/epub_builder.py`, `src/web_to_epub/core/styles.py`
- **Test spec:** see above (verify by reading the bytes back, not by inspecting builder internals)
- **Test command:** `.venv/bin/python -m pytest tests/core/test_epub_builder.py`
- **RED gate:** Assertion failures on chapter count/TOC/metadata against a stub builder returning an empty EPUB; import/setup errors are wrong-reason
- **GREEN gate:** All tests pass
- **Architectural constraints:** Pure (bytes in, bytes out, `io.BytesIO`, no temp files, no network)

---

### Phase 5: Image Fetcher (L3 Shell, real HTTP)
**Goal:** Download images safely using the policy.

**Test Spec (Behavioral):**
- Against a real local HTTP server in the test (loopback is normally blocked, so the fetcher exposes an explicit `allow_loopback_for_tests` switch, defaulting to off): an image URL returns its bytes and content type.
- With the switch off, a loopback URL is refused without any request being made.
- A redirect to a blocked address is refused (the redirect target is re-validated); redirect loops are cut off.
- A response larger than the cap is aborted, not fully downloaded; a slow response times out; a non-image content type is rejected; TLS verification is on by default.
- A failure of any kind returns a warning result, never raises to the caller.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Fetcher tests pass with a local server; no external network needed

#### Agent Context
- **Files to create:** `tests/shell/test_image_fetcher.py`, `src/web_to_epub/shell/image_fetcher.py`
- **Test spec:** see above
- **Test command:** `.venv/bin/python -m pytest tests/shell/test_image_fetcher.py`
- **RED gate:** Assertion failures against a stub fetcher that returns nothing (for example expected bytes are missing); import errors and server-startup errors are wrong-reason
- **GREEN gate:** All tests pass
- **Architectural constraints:** Resolve DNS then validate resolved IPs then connect to that IP (avoid DNS rebinding); use only `policy` decisions; no internal mocks (use the real local server)

---

### Phase 6: Convert Use Case (L3 Feature)
**Goal:** Orchestrate uploaded files to EPUB bytes plus warnings.

**Test Spec (Behavioral):**
- Given files in a caller-specified order and metadata, returns EPUB bytes whose chapters follow that order; without a specified order, natural filename order is used.
- Remote images in the markdown are fetched and embedded; one failing image yields a warning naming the URL and the rest of the book still builds.
- Errors as structured results: no files; a non-UTF-8 file (names the file); a non-`.md`/`.markdown`/`.txt` file (names the file); total size over the limit; missing title or author.
- Optional `strip_suffix` is applied to all chapter titles.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Integration tests pass using the real local HTTP server and real builder

#### Agent Context
- **Files to create:** `tests/shell/test_convert.py`, `src/web_to_epub/shell/convert.py`
- **Test spec:** see above
- **Test command:** `.venv/bin/python -m pytest tests/shell/test_convert.py`
- **RED gate:** Assertion failures against a stub `convert` returning an error result (for example chapter order or embedded-image assertions fail); import errors are wrong-reason
- **GREEN gate:** All tests pass
- **Architectural constraints:** Depends on core and `image_fetcher`; no Flask imports; no internal mocks

---

### Phase 7: HTTP Routes (L4 Contract)
**Goal:** Expose conversion over HTTP.

**Test Spec (Behavioral, contract):**
- `GET /` returns 200 HTML containing the upload UI.
- `POST /convert` multipart (fields: `files` repeated, `order` as a JSON list of filenames, `title`, `author`, optional `language`, `description`, `strip_suffix`, optional `cover`) returns 200 with `Content-Type: application/epub+zip`, a `Content-Disposition` attachment filename derived from the title, and a body that reads back as an EPUB with the expected chapters. Warnings are returned in an `X-Warnings` header (count) or a follow-up field.
- 400 with `{ "error": "<message>" }` for no files, bad encoding, wrong file type, missing title or author, and malformed `order`; 413 for an oversized request.
- No files remain on disk after any request.

**Tasks:** RED, verify, implement, refactor.

**Verification:**
- [ ] Contract tests pass with the Flask test client

#### Agent Context
- **Files to create:** `tests/shell/test_app.py`, `src/web_to_epub/shell/app.py`
- **Test spec:** see above
- **Test command:** `.venv/bin/python -m pytest tests/shell/test_app.py`
- **RED gate:** Assertion failures on status codes and content type against an app factory whose `/convert` returns 501; import errors are wrong-reason
- **GREEN gate:** All tests pass
- **Architectural constraints:** Routes are thin (parse, call `convert`, map results to HTTP); enforce `MAX_CONTENT_LENGTH`; bind to `127.0.0.1` by default

---

### Phase 8: Drag-and-Drop UI [no-test]
**Goal:** The page the user actually sees.

**Tasks:**
1. Dropzone accepting multiple `.md` files (and click-to-browse).
2. Sorted file list using natural order; drag handles to reorder (with keyboard-accessible move up/down buttons); remove button per file.
3. Metadata form (title, author required; language, description, strip-suffix, cover optional).
4. "Build EPUB" button: POST to `/convert`, show progress and errors, trigger download, list warnings.
5. Plain HTML/CSS/JS, no build step; follows system light/dark.

**Verification:**
- [ ] Drop 3 files, reorder, build: downloaded EPUB has chapters in the shown order
- [ ] An error response (for example no title) shows its message inline
- [ ] Keyboard-only reordering works; layout is usable at phone width

#### Agent Context
- **Files to create/modify:** `src/web_to_epub/shell/static/index.html`, `static/app.js`, `static/app.css`; wire static serving in `app.py` if not already done
- **Commands to run:** `.venv/bin/flask --app web_to_epub.shell.app run` and exercise it in a browser
- **Acceptance gate:** The manual checks above pass and `python -m pytest` still passes
- **Architectural constraints:** No frameworks or bundlers; the UI only talks to `POST /convert`

---

### Phase 9: Full Integration and Docs
**Goal:** Verify the whole and document it.

**Tasks:**
1. Run the complete suite.
2. Manual smoke: convert the real `../wenderweald_ebook/individual_chapters/*.md` through the UI (with strip-suffix ` - Odinson Games` and a cover) and open the result in an EPUB reader; compare against the Pandoc-built EPUB (chapter count, images present).
3. `README.md`: setup, run, usage, how it maps from the Wenderweald scripts, and the milestone-2 direction.

**Verification:**
- [ ] `python -m pytest` passes with no skips
- [ ] Wenderweald smoke build has 14 chapters and its images
- [ ] Acceptance criteria above all verified

#### Agent Context
- **Test command:** `.venv/bin/python -m pytest`
- **Acceptance gate:** All acceptance criteria from the top of this plan verified

## Constraints & Considerations

### Architectural
- Functional core, imperative shell: `core` is pure (bytes/strings in and out); all network and Flask code lives in `shell`.
- `Chapter` is source-agnostic. Milestone 2 adds an HTML source (fetch index, follow links in order, extract content region, strip shared footer) that yields the same `Chapter`s; no builder or UI rework.
- Python 3.14 is what is installed; ebooklib compatibility is checked in Phase 0.

### Testing
- Test at boundaries (L3 core/feature, L4 HTTP); no internal mocks. The fetcher is tested against a real local HTTP server.
- Property tests (hypothesis) for ordering, XML well-formedness, image-count consistency and the private-IP policy.
- Verify EPUBs by reading them back, not by asserting builder internals. `epubcheck` is not installed; adding it as an optional check is deferred.

### Performance
- In-memory processing only; cap total upload size (default 50 MB) and image size (default 10 MB); fetch images concurrently with a small worker pool and per-image timeout.

### Security
- Even as a local tool, image fetching is SSRF-guarded (scheme allowlist, resolved-IP checks, redirect re-validation, DNS-rebinding-safe connect) with TLS verification on.
- Sanitize raw HTML in markdown (`nh3`); XHTML output must be well-formed.
- Server binds to `127.0.0.1` by default; hosting publicly is a separate decision that needs rate limits and auth.

## Out of Scope

- **URL/website scraping (learntarot.com)**: milestone 2, planned as a separate plan built on this core.
- Public hosting, accounts, persistence, rate limiting.
- CLI (trivial once the core exists; add if wanted).
- Pandoc integration; cover generation; per-site config files.
- Nested TOC (sub-chapters within a file); multiple books per session.
- `epubcheck` in CI.

## Approval Checklist

- [ ] All files to create/modify listed
- [ ] Phases have clear boundaries
- [ ] Each phase has an Agent Context block
- [ ] Test specs are behavioral
- [ ] Acceptance criteria are testable
- [ ] Constraints documented
- [ ] Out-of-scope noted
