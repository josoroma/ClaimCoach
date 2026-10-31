# Review: US-7.3

Change: us-7-3-no-send-submit
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The contribution walk read only a control's own string props: text nested in a control, labels next to inputs, and memo/forwardRef components were never collected | The walk collects all text inside a control or `<label>`, label props and every `aria-*` text, every link and form target, and expands function, memo, and forwardRef components; "the check catches a send control" now proves each shape (nested span, icon plus text, label with a checkbox, memo, forwardRef, placeholder, `aria-description`) |
| high | The import and client scan missed `from http import client`, `from httpx import AsyncClient`, aliased httpx, sockets, `asyncio.open_connection`, subprocesses, and `importlib` | One `scan()` reads `module.name` imports, tracks every name bound to httpx, and flags sockets, subprocesses, and imports by name; HTTP clients, sockets, and subprocesses are pinned per module with what each reaches; `test_us_7_3_the_scan_catches_a_way_out` (14 bypass samples), `test_us_7_3_the_scan_passes_plain_code` |
| medium | The route walk skipped Starlette routes, websockets, and mounts | Every route type is enumerated (websockets as `WS`, mounts recursed) and an unknown type fails; `test_us_7_3_the_route_walk_sees_every_route_type` |
| medium | The pane's word list was narrower than the backend's and missed "Resend", "payer portal", "file with", and absolute links | Wider list without a leading word boundary for `send`; any absolute or protocol-relative `href`/`action` fails |
| medium | The loopback flow skipped the upload and field-confirm routes | The flow uploads a document and confirms a field too; the relay reads the job events; the docstring says why the worker's `/redact` is not reachable from the gateway |
| low | The "scan catches" test never ran the scanner | It runs `scan()` on each sample |
| low | Production endpoint locality was checked by an exact source string | Every `ModelEndpoint(...)` call is checked by AST to build its URL on `LOOPBACK`, and `LOOPBACK == "127.0.0.1"` |
| low | The plugin.js scan missed `openExternal`, `location.*`, `navigator.share`, dynamic `import(`, and URL literals | Added, with comments stripped first |
| low | The BR-4 docstring test listed `letters/` files by name | It globs `letters/*.py` |
| low | Settings pages could go unwalked silently | The test asserts one settings page was collected |
| info | Tasks unchecked, evidence missing | Evidence recorded by the independent `story-tester`; tasks checked before archive |

Also checked by the reviewer and found sound: the pinned gateway and worker route sets; `DownloadRequest`/`ConversionRequest` carrying a role and a yes/no only (BR-1); `trust_env=False` on every reviewed client; `WorkerConfig.host` typed `Literal["127.0.0.1"]`; the connect and DNS recording with the autouse socket guard (a non-loopback connect raises, so the flow cannot pass vacuously); the fake ctx's registration surface against the SDK stub.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-7 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1182 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 104 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-7.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
operator runs of `make case-draft` (with and without `TEMPLATE=`), `case-show`, `case-edit`, and
`case-export FORMAT=pdf|docx TO=…` against scratch workers with fake models and synthetic data;
the exported files were read back with pdftotext, pdfinfo, textutil, and unzip. The real-model
test `test_us_7_1_draft_real_model` ran Ternary-Bonsai-2-27B from `~/Models` through
`ModelManager` and passed (43 s), after `--reasoning off` was added (without it the same test
failed `drafting_failed`); no model server was left running.
