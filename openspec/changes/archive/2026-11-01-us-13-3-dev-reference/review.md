# Review: US-13.3

Change: us-13-3-dev-reference
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | The Uploads intro said every upload is a multipart part forwarded unparsed and typed from its bytes; paste is JSON and bundles are parsed in the gateway and chosen by file name | Rewritten per upload; the test checks the paste JSON body and the bundle's file-name rule are stated |
| medium | Bundle error answers were wrong (preview answers `valid: false` with `problem`; import answers `invalid_bundle` with a fixed message, or `import_not_confirmed`) | Documented per route, in the Uploads note and the REST table |
| medium | `main.documents` readers were wrong: the readers are the exact lookups in `corpus/lookup.py`; retrieval has no production caller | Readers listed; `chunks`, `vectors`, and the storage intro say retrieval is not called yet |
| medium | The storage table left out the decoded call `mlx_audio.server` writes to `/tmp`, `server-logs/`, `servers.json`, and `egress.jsonl` | Added, with the PHI and protection of each |
| low | "`CorpusStore` is the only code that runs SQL"; "schema version" in `main.meta`; "Tables are STRICT"; `idx.meta` keys; `case_items`/`outcomes` readers; `declined`; settings routes not proxied; worker state modes | Each corrected |
| low-medium (tests) | The table check parsed `_SCHEMA` text one way; storage names were hard-coded and paths not resolved; request examples and PHI cells were not checked | The test opens a `CorpusStore` and reads `sqlite_master`/`PRAGMA table_info` (column sets must be equal); paths are resolved against a scratch root and compared with the path functions and `WorkerConfig`; JSON examples validate against each route's request model; PHI cells must say Yes or No |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 244.06s (0:04:04) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-13.1
ok   US-13.2
ok   US-13.3
ok   US-13.4
ok   US-13.5
================ 2 passed, 1824 deselected in 248.32s (0:04:08) ================
```

The first `make verify` run failed once in its nested `make check` (the gate's self-test):
`test_us_2_2_group_members_are_stopped_with_the_leader` raised `PermissionError` from `os.killpg` in
`_group_alive` (`plugin/claimcoach/models/manager.py`, EPIC-2), which catches only
`ProcessLookupError`. It passed 5 of 5 runs alone and on the second `make verify`. This change does
not touch that code; it is reported to the user as a separate follow-up.
