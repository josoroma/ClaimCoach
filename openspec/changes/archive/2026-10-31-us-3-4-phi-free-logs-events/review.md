# Review: US-3.4

Change: us-3-4-phi-free-logs-events
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | Event ID pattern `[A-Za-z0-9_-]{1,64}` accepted ISO DOBs, SSNs, MRNs, member IDs, surnames | Opaque `case_`/`job_` + 16 hex IDs (`new_case_id`, `new_job_id`); `test_us_3_4_event_ids_reject_phi_shaped_values` over every seeded fixture value (216 cases) |
| high | Unguarded `getMessage()`: a bad log call raised into ClaimCoach callers, and for other libraries `handleError` printed a traceback and the raw arguments (PHI) to `worker.log` | Guarded message (`[unformattable log call]` + scrubbed format string); JSON `handleError`; `test_us_3_4_unformattable_log_calls_never_leak_or_raise`, `test_us_3_4_handler_errors_are_one_json_line` |
| medium | Ledger kept only exact spans; surname-only or reversed names in logs passed | Name words remembered; `test_us_3_4_ledger_remembers_each_part_of_a_name` |
| medium | End-to-end test ran in-process and its "request or job ID" check could not fail | `test_us_3_4_real_worker_process_logs_only_json` runs `python -m claimcoach.worker` and parses every stderr line; request lines must carry their own request ID |
| medium | Model-server and download/convert raw logs are not JSON or scrubbed | Scope stated in design and spec (third-party output, 0600, plugin data dir); follow-up for the retention purge (US-4.5) |
| low | Uncaught exceptions would print tracebacks | `sys.excepthook` / `threading.excepthook` → JSON type-only line; `test_us_3_4_uncaught_exceptions_are_json_type_only` |
| low | `request_id_var` never reset; background tasks inherited it | Reset after each request; tasks start in an empty context |
| low | "Worker broadcasts" needs a worker → gateway relay | Recorded as EPIC-5 scope in design and `events.py` |
| low | Fallback job ID order-dependent in tests | Fixture restores it; exact assertion |

## Re-verification

`make check` → exit 0 (710 pytest + 27 node, 100%). `make evidence STORY=US-3.4` → 231 passed.

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
