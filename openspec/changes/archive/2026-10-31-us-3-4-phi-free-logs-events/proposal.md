# Proposal: US-3.4 PHI-Free Logs and Events

## Why

Diagnostics must never expose patient data: logs are structured JSON with request/job IDs and
no document text (ES-8), and logs, events, and tool results are redacted (BR-14, PRD §10).

## What Changes

- `claimcoach.logs` (named `logs`, not `logging`, so it never shadows the standard library):
  `JsonFormatter` (one JSON object per line: `ts`, `level`, `logger`, `message`, `request_id`,
  `job_id`, optional `exc_type`), `PhiRedactionFilter` (scrubs the message, drops exception text),
  `get_logger()`, `configure_logging()`, `job_context()`, `request_id_var` / `job_id_var`.
- `claimcoach.redact.ledger.PhiLedger`: bounded in-memory set of the PHI values the redactor
  found in this process; the log scrub removes them along with regex-shaped PHI.
- `claimcoach.redact.spans`: the pure `locate` / `merge_spans` / `redact` functions, split from
  `redactor.py` so logging can use them without importing model code.
- Worker: a request ID per request (log lines and `X-Request-ID` header); the idle sweep and
  download/convert jobs log under a job ID; `python -m claimcoach.worker` logs JSON to stderr
  (`worker.log`) and runs uvicorn with `log_config=None`; an invalid `models.yaml` is a JSON log
  line instead of a `print`.
- `claimcoach.events`: typed `CaseProgressEvent` (`plugin.claimcoach.case.progress`) whose
  strings are enums or ID patterns, and `publish()` over Hermes' `broadcast_plugin_event`.
- All ClaimCoach loggers come from `get_logger()`.

## Capabilities

### New Capabilities
- `phi-free-telemetry`: JSON logs with request/job IDs and PHI scrubbing; typed PHI-free events.

### Modified Capabilities
- None (worker routes and responses are unchanged apart from the `X-Request-ID` header).

## Impact

- `worker.log` lines are JSON. The US-2.2 test for an invalid `models.yaml` reads the JSON line.
- Tests restore the root logger after each test (`tests/conftest.py`).
