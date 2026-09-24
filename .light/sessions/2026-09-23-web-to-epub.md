# web-to-epub v1 — Session Artifact

**Date:** 2026-09-23
**Plan:** `.light/sessions/web-to-epub-plan.md`
**Execution log:** `.light/sessions/2026-09-23-web-to-epub-execution.md`
**Tracker:** yaks, epic `web-to-epub-v1` (all 10 phases done)

## Research Summary

No separate research phase. The plan's Context section carries the findings:

- `../wenderweald_ebook` converts Substack markdown exports to EPUB with two hard-coded scripts (`process_chapters.py`, `build_epub.sh` via Pandoc).
- The long-term goal is also to turn a website's lessons into an EPUB (starting with learntarot.com). That is milestone 2, and the v1 core is designed so a URL source can plug in.
- Decisions made with the user: Python + Flask + ebooklib (no Pandoc), local tool first, markdown upload first, natural filename sort plus drag to reorder, stateless.

## Plan Summary

Functional core, imperative shell.

| Phase | What | Layer |
|---|---|---|
| P1 | Project scaffold (src layout, venv, CLAUDE.md) | no-test |
| P2 | `core.ordering.natural_sort` | L3 core |
| P3 | `core.markdown_chapter.parse_chapter`, `core.models` (`Chapter`, `ImageRef`) | L3 core |
| P4 | `core.image_policy` (SSRF and size/type policy, pure) | L3 core |
| P5 | `core.epub_builder.build_epub`, `core.styles` | L3 core |
| P6 | `shell.image_fetcher` (real local HTTP server tests, DNS-rebinding-safe connect) | L3 shell |
| P7 | `shell.convert` use case | L3 feature |
| P8 | `shell.app` Flask routes (`GET /`, `POST /convert`) | L4 contract |
| P9 | Drag-and-drop UI + README | no-test |
| P10 | Full integration validation | validate |

Architectural decisions: `core` is pure and never imports `shell` or Flask. `Chapter` is source-agnostic. Remote images are fetched with SSRF guards and TLS verification on. Nothing is written to disk. The server binds to 127.0.0.1.

## Execution Log

Summary of `2026-09-23-web-to-epub-execution.md`:

- 25 agent dispatches. RED, GREEN and VALIDATE gates all passed for every TDD phase (RED 8, GREEN 7, VALIDATE 8).
- 4 gate failures, 3 remediations. All were resolved:
  - **P4 RED (wrong reason).** The test agent didn't create the accept-everything stub, so collection failed on import. The agent was sent back to add the stub; it then failed at assertions.
  - **P5 GREEN.** `test_stylesheet_included_and_linked_from_every_chapter` was defective: ebooklib's read-back drops each chapter's `<head>`. Fixed by reading the raw zip. Strictness verified by mutation.
  - **P7 GREEN.** The cover assertion was defective: ebooklib types the cover as `ITEM_COVER` on read-back. Fixed with a separate `covers()` helper. Strictness verified by mutation.
  - **P8 GREEN.** The route test counted the EPUB3 nav document as a chapter. Fixed. A real bug was found at the same time: `convert()` raised `KeyError` (a 500 from the API) when `order` named a file that wasn't uploaded. Six tests were added, and `convert` now returns `ConvertError(code="bad_order")`, which the route maps to a 400.
- In each case the orchestrator confirmed the diagnosis independently before routing the fix to the right agent. Test files were never edited by implementer agents.
- One implementer report (P3) said only "placeholder". The orchestrator checked the state directly (13 tests pass, tests untouched, core imports clean) before closing.
- After P10, the user asked for a Playwright visual review. A Haiku agent produced incremental notes, and the orchestrator added its own critique. A restyle pass then rewrote `app.css`, `index.html` and `app.js` (render, button and error handling only). It was verified with Playwright.

## Outcome

**Final test suite:** `.venv/bin/python -m pytest` → 178 passed, 0 skipped. No linter or type-checker is configured for this project.

**Wenderweald smoke test** (orchestrator-verified against the reference EPUB): 14 chapters and 37 images embedded (reference has 36), 0 warnings. Chapter titles and author match. `mimetype` is the first zip entry.

**Acceptance criteria:**

| # | Criterion | Status |
|---|---|---|
| 1 | N files → N chapters in displayed order, TOC lists titles | Verified (tests; UI Playwright check; smoke) |
| 2 | Natural sort; dragging changes build order | Verified (tests; Playwright mouse drag-and-drop and keyboard reorder) |
| 3 | Title from first H1, suffix stripping, filename fallback | Verified (tests; smoke) |
| 4 | Failed image → warning, never a failed build | Verified (tests) |
| 5 | Fetcher refuses bad schemes, private/loopback/link-local, oversize, slow | Verified (tests against a real local server) |
| 6 | Titled image → `<figure>`; linked images unwrapped | Verified (tests) |
| 7 | Optional cover becomes EPUB cover | Verified (tests; smoke) |
| 8 | EPUB reads back cleanly with ebooklib | Verified. **Not verified:** opening in an actual EPUB reader (`epubcheck` is not installed; deferred per plan) |
| 9 | Bad input → clear 4xx shown in UI | Verified (tests; Playwright inline error) |
| 10 | Nothing written to disk that outlives the request | Verified by a test that watches temp dir and cwd |
| 11 | Wenderweald smoke test | Verified |

## Simplify pass (post-review)

Four read-only reviewers (reuse, simplification, efficiency, altitude) reported; fixes applied by the orchestrator, suite re-run after each group (178 passed).

**Applied:**
- `core/image_policy`: added `media_type()`; `check_address`/`check_url` take an optional `allow_loopback=False` (default-deny unchanged). Removed the fetcher's `_is_allowed`/`_check_url` (including the `url.replace(host, "localhost")` hack) and the duplicate `check_address` call.
- `shell/image_fetcher`: one URL parse per hop, one TLS context per fetch (was per hop), `b"".join` instead of `bytearray` + copy, uses `DEFAULT_MAX_BYTES` and `media_type`.
- `shell/convert`: distinct remote images fetched concurrently (`ThreadPoolExecutor`, 5 workers, `pool.map` so warning order, dedup and `images` content stay deterministic). This closes the plan's concurrent-fetch item. Real Wenderweald run: 14 chapters, 37 images, 0 warnings, 1.5s (no baseline timing was taken).
- `shell/app`: Flask defaults for static config, `send_static_file`, `request.form` read once.
- `static/app.js`: `byName` comparator, shared `reorder()` for drag and buttons, tidier row construction. `static/app.css`: removed unused `--elevated`. Re-verified with Playwright (sort, duplicate skip, keyboard move + focus, mouse drag, live-region announcements, missing-title error, downloaded EPUB order).

**Skipped (with reason):**
- Changes to test-pinned interfaces: passing a policy through `Options`, `ConvertError` carrying an HTTP status, moving `ImageData` into `models`.
- Replacing the regex in `epub_builder` (`<img src>` rewrite) and the title regex in `markdown_chapter` with parser-based approaches: larger than a cleanup pass.
- `except Exception` in `fetch_image`: deliberate ("never raise to the caller").
- Per-host connection pooling, single reused `Markdown` instance, memory-copy trims in `app.py`/`epub_builder`: negligible at this scale.
- Duplicate `.dropzone:focus-visible` rule: differs by outline offset (3px vs 2px), removing it changes the look.
- Extension whitelist duplicated in Python and JS: inherent; a sync comment was added.

## Post-simplify bugfix: headings inside fenced code

Found during the simplify pass and confirmed by a test agent: `parse_chapter` picked the title with a regex over raw markdown source, so a `# comment` inside a ``` or ~~~ fence became the chapter title (and was rewritten by `strip_suffix`); also `fenced_code` was not enabled, so fences rendered as paragraphs and the comment became a real `<h1>`. Fixed test-first (5 failing tests, then implementation): `fenced_code` enabled, title taken from the first rendered `<h1>` with the suffix stripped there. Suite: 185 passed. Behaviour change: inline markdown in a title (`# *Foo*`) now yields plain-text `Foo`. Wenderweald re-smoke: 14 chapters, 36 images (the earlier run counted 37 including the cover), 0 warnings; 13 of 14 titles match the reference EPUB, the 14th differs only by a straight vs curly apostrophe (source has a straight one; the Pandoc reference applies smart typography).

## Known gaps and follow-ups

- **Fetch timeout is per socket operation**, not a total deadline. A slow-drip response could hold a fetch open. Acceptable for a local single-user tool.
- **`X-Warnings` is a count only.** The UI cannot show which image URLs failed.
- **UI not verified** in Safari or Firefox, or on real touch devices. Live-region announcement text after keyboard reorder wasn't re-read after the restyle.
- **EPUB not opened in a real reader**, and `epubcheck` not run.
- **Git:** no commits exist yet. Everything is untracked.
- **Milestone 2:** URL scraping (learntarot.com) via an HTML source that yields the same `Chapter`s.
