# Test Report: US-3.4 PHI-Free Logs and Events

Change: us-3-4-phi-free-logs-events
Story: US-3.4
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), run after implementation and independent review
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Logs are structured JSON without document text: Then every log line is valid JSON with a request or job ID and no log line contains a seeded PHI string or document text" | PASS | `test_us_3_4_logs_json_without_document_text`: `configure_logging("worker")` + a live worker (uvicorn, `log_config=None`) whose model manager starts a fake PHI model-server **process**; the run redacts a three-document case, sends a bad token, raises an error whose message is the whole case text, routes a tool result through the guard, and logs a careless line quoting the patient's name and SSN inside `job_context("case-0001")`. Every captured line parses as JSON, has `request_id` or `job_id`, and contains no seeded string and no document line (≥ 20 chars); the careless line reads `case for [NAME] ([SSN]) stalled`. `test_us_3_4_exception_text_is_never_logged`, `test_us_3_4_foreign_loggers_are_scrubbed_by_the_formatter` |
| 2 | "Broadcast events carry no PHI: Then no event payload contains a seeded PHI string" | PASS | `test_us_3_4_events_carry_no_phi`: progress events for the case through every stage (and a failure) go to `("claimcoach", "case.progress", payload)`; the serialized payloads contain no seeded string or document line. `test_us_3_4_event_payloads_reject_free_text` (6 cases) and `test_us_3_4_event_fields_cannot_carry_text` (schema walk: every string is enum/const/ID pattern). `test_us_3_4_publish_uses_hermes_broadcast_inside_the_gateway` |

## Evidence Commands

```bash
make evidence STORY=US-3.4
```

```text
===================== 231 passed, 483 deselected in 3.09s ======================
```

Artifacts: `evidence/US-3.4/junit.xml`

## Failures

None.

## Notes

- "Processed end to end" covers what the worker processes today (redaction, auth, errors, model
  server start, the tool guard). The case pipeline routes arrive with EPIC-5 and log through the
  same formatter.
- The worker emits progress events through `publish()`; the gateway relay of worker events lands
  with the EPIC-5 job pipeline, so no event was observed on a live Desktop client.
- Module is `claimcoach/logs.py` rather than `logging.py` (design decision 1).
- After independent review: event IDs are opaque (`case_`/`job_` + 16 hex) and every seeded value
  of every fixture is rejected in either ID field (`test_us_3_4_event_ids_reject_phi_shaped_values`,
  216 cases); unformattable log calls, handler errors, and uncaught exceptions write one JSON line
  without arguments or messages; name words are remembered by the ledger; request IDs are reset
  after each request and background tasks start in a clean context;
  `test_us_3_4_real_worker_process_logs_only_json` runs `python -m claimcoach.worker` as a process
  and parses every line of its stderr log.
- Scope: model-server and download/convert raw output (`models/<port>.log`, `acquire-<role>.log`)
  is third-party output kept at mode 0600 under the plugin data dir; it is out of this story's
  scope and must be covered by the retention purge (US-4.5).
