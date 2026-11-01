# Test Report: US-13.3 Data, API, Storage, and Upload Reference

Change: us-13-3-dev-reference
Story: US-13.3
Verdict: pass
Coverage: 7/7 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Every gateway route is documented: Then each route is listed with its method, path, request body, and response model" | PASS | `test_us_13_3_routes_documented`: the REST table has exactly the 27 routes of `claimcoach.api.routes.router`; each response cell names its `response_model`; each JSON request example validates against the route's request model; multipart routes say `multipart \`file\``; GET routes have no body |
| 2 | "Every gateway route is documented: And a test fails when a route is added, removed, or changes its response model without the guide" | PASS | Same test: set equality on `(method, path)`; a POST route without a known request model fails until it is added |
| 3 | "Every table is documented with its writers and readers: Then each table and index table is listed with its columns, what writes it, and what reads it" | PASS | `test_us_13_3_tables_documented`: a `CorpusStore` is opened in `tmp_path` and both files' `sqlite_master` and `PRAGMA table_info` are read; the guide's tables and column sets equal them exactly (9 tables); each row says what writes and reads it and whether it holds PHI; the `case_items` kinds equal `CaseItemKind` |
| 4 | "Every table is documented with its writers and readers: And a test fails when a table is missing from the guide" | PASS | Same test, set equality against the live schema |
| 5 | "Uploads are documented with the limits the code enforces: Then each lists its route, accepted types, and size limit" | PASS | `test_us_13_3_upload_limits_match_code`: document, paste, call recording, and corpus bundle rows, each with a gateway route, accepted types (WAV, MP3, FLAC, M4A from `AudioFormat`), and where it goes; the paste JSON body and the bundle's file-name rule are stated |
| 6 | "Uploads are documented with the limits the code enforces: And the limits in the guide equal the limits in the code" | PASS | Same test: 16 MiB (`MAX_FILE_BYTES`), 4 MiB (`MAX_PASTE_BYTES`), 128 MiB (`MAX_CALL_BYTES`), 5 MiB (`MAX_BUNDLE_BYTES`), up to 5000 items (`MAX_ITEMS`) |
| 7 | "Every place ClaimCoach stores data is documented: Then each is listed with its path, what it holds, whether it holds PHI, and how it is protected" | PASS | `test_us_13_3_storage_documented`: each documented path is resolved against a scratch root with profile `p` and must equal the code's path function (`global_scope_dir`, `profile_user_scope_dir`, `profile_exports_dir`, `fine_tune_dir`, `transcription_dir`, `WorkerConfig.state_dir`, `models.yaml`, `models/`); the files they hold (`token`, `worker.json`, `worker.log`, `egress.jsonl`, `servers.json`, …) are named; the user scope, exports, and the transcription temp file are marked PHI |

## Evidence Commands

```bash
make evidence STORY=US-13.3
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
====================== 5 passed, 1821 deselected in 1.41s ======================
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 250.31s (0:04:10) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.3/junit.xml`

## Failures

None.

## Notes

- Writing and reviewing this reference surfaced facts now stated in the guide: no pipeline step writes the user scope's `documents`/`chunks` or calls retrieval yet (the diagnosis and drafts use exact lookups in `corpus/lookup.py`), so the `rerank` model does not start in a case flow; and `mlx_audio.server` may leave a decoded call in `/tmp` after a crash.
- Review fixes (see review.md): the upload paths for paste and bundles, the bundle error answers, the `documents` readers, `main.meta` keys, `STRICT`, and the storage table were corrected; the tests now read the live schema and the path functions.
