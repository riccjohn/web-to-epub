# Execution Log — web-to-epub-v1
[DISPATCHED] P1-Project-Scaffold — agent type: no-test, mode: sync
[GATE PASS] P1-Project-Scaffold — acceptance gate passed
[CLOSED] P1-Project-Scaffold
[DISPATCHED] P2-Chapter-Ordering/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P2-Chapter-Ordering/01-write-tests — RED gate passed (7 failed at assertions)
[CLOSED] P2-Chapter-Ordering/01-write-tests
[DISPATCHED] P2-Chapter-Ordering/02-implement — agent type: agent-impl, mode: sync
[GATE PASS] P2-Chapter-Ordering/02-implement — GREEN gate passed (10 passed)
[CLOSED] P2-Chapter-Ordering/02-implement
[DISPATCHED] P2-Chapter-Ordering/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P2-Chapter-Ordering/03-validate — VALIDATE gate passed (11 passed)
[CLOSED] P2-Chapter-Ordering/03-validate
[DISPATCHED] P3-Markdown-Chapter/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P3-Markdown-Chapter/01-write-tests — RED gate passed (9 failed at assertions)
[CLOSED] P3-Markdown-Chapter/01-write-tests
[DISPATCHED] P3-Markdown-Chapter/02-implement — agent type: agent-impl, mode: sync
[GATE PASS] P3-Markdown-Chapter/02-implement — GREEN gate passed (13 passed, verified by orchestrator; agent report was only "placeholder")
[CLOSED] P3-Markdown-Chapter/02-implement
[DISPATCHED] P3-Markdown-Chapter/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P3-Markdown-Chapter/03-validate — VALIDATE gate passed (24 passed)
[CLOSED] P3-Markdown-Chapter/03-validate
[DISPATCHED] P4-Image-Policy/01-write-tests — agent type: agent-test, mode: sync
[GATE FAIL] P4-Image-Policy/01-write-tests — RED gate failed: wrong-reason RED (ImportError, no accept-everything stub); asking agent-test to add stub
[GATE PASS] P4-Image-Policy/01-write-tests — RED gate passed after stub added (63 failed at assertions)
[CLOSED] P4-Image-Policy/01-write-tests
[DISPATCHED] P4-Image-Policy/02-implement — agent type: agent-impl, mode: sync
[GATE PASS] P4-Image-Policy/02-implement — GREEN gate passed (81 passed)
[CLOSED] P4-Image-Policy/02-implement
[NOTE] check_url raises ValueError on malformed URLs like "http://[bad" (untested); P6 fetcher must handle
[DISPATCHED] P4-Image-Policy/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P4-Image-Policy/03-validate — VALIDATE gate passed (105 passed, verified by orchestrator)
[CLOSED] P4-Image-Policy/03-validate
[DISPATCHED] P5-Epub-Builder/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P5-Epub-Builder/01-write-tests — RED gate passed (13 failed at assertions; read-back helper untested against real EPUB — caveat)
[CLOSED] P5-Epub-Builder/01-write-tests
[DISPATCHED] P5-Epub-Builder/02-implement — agent type: agent-impl, mode: sync
[GATE FAIL] P5-Epub-Builder/02-implement — GREEN gate failed: 12/13; test_stylesheet_included_and_linked_from_every_chapter is defective (ebooklib read-back drops <head>; raw zip verified to contain the link). Routing test fix to agent-test.
[REMEDIATION] P5-Epub-Builder/02-implement — attempt 1: test defect fixed by agent-test (raw-zip link check); strictness verified via mutation
[GATE PASS] P5-Epub-Builder/02-implement — GREEN gate passed (13 passed)
[CLOSED] P5-Epub-Builder/02-implement
[DISPATCHED] P5-Epub-Builder/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P5-Epub-Builder/03-validate — VALIDATE gate passed (118 passed)
[CLOSED] P5-Epub-Builder/03-validate
[DISPATCHED] P6-Image-Fetcher/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P6-Image-Fetcher/01-write-tests — RED gate passed (6 failed at assertions, 13 pass vacuously vs stub but guarded by positive controls)
[CLOSED] P6-Image-Fetcher/01-write-tests
[DISPATCHED] P6-Image-Fetcher/02-implement — agent type: agent-impl, mode: sync
[GATE PASS] P6-Image-Fetcher/02-implement — GREEN gate passed (19 passed; full suite 137)
[CLOSED] P6-Image-Fetcher/02-implement
[NOTE] image_fetcher timeout is per-socket-op, not a total deadline (slow-drip could hold a fetch open); acceptable for local single-user tool
[DISPATCHED] P6-Image-Fetcher/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P6-Image-Fetcher/03-validate — VALIDATE gate passed (137 passed)
[CLOSED] P6-Image-Fetcher/03-validate
[DISPATCHED] P7-Convert-Use-Case/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P7-Convert-Use-Case/01-write-tests — RED gate passed (19 failed at assertions)
[CLOSED] P7-Convert-Use-Case/01-write-tests
[DISPATCHED] P7-Convert-Use-Case/02-implement — agent type: agent-impl, mode: sync
[GATE FAIL] P7-Convert-Use-Case/02-implement — GREEN gate failed: 18/19; test_metadata_and_optional_cover defective (helper images() only reads ITEM_IMAGE; ebooklib types cover as ITEM_COVER on read-back; verified). Routing test fix to agent-test.
[REMEDIATION] P7-Convert-Use-Case/02-implement — attempt 1: test defect fixed by agent-test (ITEM_COVER helper); strictness verified via mutation
[GATE PASS] P7-Convert-Use-Case/02-implement — GREEN gate passed (19 passed)
[CLOSED] P7-Convert-Use-Case/02-implement
[DISPATCHED] P7-Convert-Use-Case/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P7-Convert-Use-Case/03-validate — VALIDATE gate passed (156 passed; arch checks verified)
[CLOSED] P7-Convert-Use-Case/03-validate
[DISPATCHED] P8-HTTP-Routes/01-write-tests — agent type: agent-test, mode: sync
[GATE PASS] P8-HTTP-Routes/01-write-tests — RED gate passed (15 failed at assertions, 1 GET / placeholder passes)
[CLOSED] P8-HTTP-Routes/01-write-tests
[DISPATCHED] P8-HTTP-Routes/02-implement — agent type: agent-impl, mode: sync
[GATE FAIL] P8-HTTP-Routes/02-implement — GREEN gate failed: 15/16; test_convert_returns_epub_with_headers defective (_chapter_texts counts EpubNav; verified). Also verified real bug: convert() raises KeyError for order naming a non-uploaded file (500 via API). Routing to agent-test: fix helper + add failing tests for unknown/duplicate order names (convert -> ConvertError, route -> 400); then agent-impl fixes.
[GATE PASS] P8-HTTP-Routes tests updated — helper fixed; 6 new bad-order tests RED (fail in code under test)
[REMEDIATION] P8-HTTP-Routes/02-implement — attempt 1: implement bad_order validation in shell/convert.py (+ route mapping)
[GATE PASS] P8-HTTP-Routes/02-implement — GREEN gate passed (178 passed)
[CLOSED] P8-HTTP-Routes/02-implement
[DISPATCHED] P8-HTTP-Routes/03-validate — agent type: agent-validate, mode: sync
[GATE PASS] P8-HTTP-Routes/03-validate — VALIDATE gate passed (178 passed)
[CLOSED] P8-HTTP-Routes/03-validate
[DISPATCHED] P9-Drag-Drop-UI — agent type: no-test, mode: sync
[GATE PASS] P9-Drag-Drop-UI — acceptance gate PARTIAL: logic verified in jsdom against live server (order, inline title error, dup/unsupported skips, EPUB chapter order); 178 tests pass
[NOTE] P9 NOT verified in a real browser: HTML5 mouse drag-and-drop, real Tab/Enter focus rings, download prompt, light/dark theme, phone layout. Needs manual check.
[CLOSED] P9-Drag-Drop-UI
[DISPATCHED] P10-Full-Integration — agent type: agent-validate, mode: sync
[GATE PASS] P10-Full-Integration — VALIDATE gate passed (178 passed, 0 skips); smoke verified by orchestrator: 14 chapters, 37 images (ref 36), 0 warnings, titles match reference
[CLOSED] P10-Full-Integration
[NOTE] User requested a Playwright/Haiku visual design review + restyle of the UI after P10; final verification/session artifact deferred until restyle is done
[DISPATCHED] UI-Restyle — agent type: no-test (user-requested post-P10 design pass, from Haiku/Playwright review + orchestrator critique), mode: sync
[SESSION] artifact and manifest written: .light/sessions/2026-09-23-web-to-epub.md / .manifest.json
[SIMPLIFY] 4 reviewers; fixes applied (policy loopback kwarg + media_type, fetcher cleanup, concurrent image fetch, app.py, app.js reorder/byName, css); 178 passed; Playwright functional re-check passed; Wenderweald smoke 14/37/0
[REDGATE] bugfix: title/H1 inside fenced code blocks — 5 new tests fail at assertions (backtick+tilde), 2 indented-code guards pass; 180 pass
[DISPATCHED] bugfix fenced-code title — agent type: agent-impl
[BUGFIX] fenced-code title bug fixed test-first; 185 passed; Wenderweald 14 chapters/0 warnings; titles match ref except apostrophe style (source straight, ref curly)
