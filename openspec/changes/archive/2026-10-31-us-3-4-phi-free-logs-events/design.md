# Design: US-3.4 PHI-Free Logs and Events

## Context

Python logging runs synchronously, sometimes inside the redactor's own request, and in the
gateway its records go to handlers Hermes owns. The PHI model cannot be called from a log call.
Hermes delivers plugin events with `broadcast_plugin_event(plugin_id, event, payload)` from the
gateway process only (PC-4).

## Goals / Non-Goals

**Goals:** every worker log line is JSON with a request or job ID; no line carries a seeded PHI
string or document text, even when a log call is careless or an exception quotes its input;
event payloads cannot carry PHI.

**Non-Goals:** shipping logs anywhere; the case pipeline that emits progress (EPIC-5) — this
story defines the payload and the publisher it will use; the relay of worker progress to the
gateway (only the gateway has Hermes' broadcaster) — part of the EPIC-5 job pipeline. Scope of
"log": the worker's and the gateway's ClaimCoach log lines. The raw output of the model servers
and download/convert tools (`models/<port>.log`, `acquire-<role>.log`, mode 0600, under the plugin
data dir) is third-party output, not ClaimCoach log lines; it is out of scope here and must be
covered by the retention purge (US-4.5).

## Decisions

1. **Module name `claimcoach/logs.py`.** SPECS names `claimcoach/logging.py`; a module named
   `logging` inside the package shadows the standard library for readers and trips ruff A005.
   *Alternative:* keep the name with a file-level noqa — rejected, confusing imports.
2. **Scrub without the model: regex validators + a PHI ledger.** The ledger holds the values the
   redactor found in this process (names and addresses the regex cannot see), bounded at 10 000
   values, in memory only. The scrub is `redact(message, ledger_spans)` — the same placeholders
   and second-pass regex as US-3.1. *Alternative:* call `/redact` from the log path — rejected,
   recursive and blocking.
3. **Two layers.** `PhiRedactionFilter` on every ClaimCoach logger (protects records that reach
   Hermes' handlers in the gateway) and the scrub again in `JsonFormatter` (protects records of
   other libraries, e.g. uvicorn, in the worker). Logger-level filters do not apply to child
   loggers, so `get_logger()` attaches the filter to each logger by name.
4. **Exception text is never written** — only `exc_type`. Messages and tracebacks routinely quote
   their input (`ValueError(f"cannot parse {text}")`).
5. **IDs from context variables.** The worker middleware sets `request_id_var` per request;
   `job_id_var` is set at the start of the idle-sweep task and each download/convert task (their
   own contexts) and by `job_context()`. A line outside any request or job (startup) gets the
   process as its job ID: `process-<pid>` by default, `worker-<pid>` once the worker's
   `configure_logging("worker")` ran.
6. **Events are PHI-free by construction.** Every string field of an event payload is an enum or
   an opaque ID ClaimCoach generates: `case_` or `job_` plus 16 hex digits (`new_case_id`,
   `new_job_id`); `extra="forbid"`. The first pattern (`[A-Za-z0-9_-]{1,64}`) accepted ISO DOBs,
   SSNs, MRNs, and surnames (review finding, high); a test now rejects every seeded value of the
   fixture set in either ID field. *Alternative:* redact payloads at publish time — rejected, an
   opaque-ID contract cannot leak, a redactor can.
7. **A bad log call never leaks or raises** (review finding, high). `getMessage()` is guarded:
   arguments that do not fit the format string are dropped and the scrubbed format string is
   written with an `[unformattable log call]` marker. The handler's own errors become one JSON
   line with the error type (`handleError`), and `configure_logging` routes `sys.excepthook` and
   `threading.excepthook` to a JSON line with the exception type only.
8. **Request IDs are scoped** (review finding). The middleware resets `request_id_var` after each
   request, and background tasks (model starts and stops, downloads) start in an empty context.
9. **Name words in the ledger** (review finding). Each word of a found name is remembered too, so
   a log line quoting only the surname or the reversed form is scrubbed.

## Risks / Trade-offs

- [A name never seen by the redactor is logged] → log calls pass codes, roles, ports, and types
  only (reviewed); the ledger catches names found in any document of the process.
- [Ledger holds PHI in memory] → same process that already holds the documents; bounded; never
  written or returned; cleared on restart.
- [Over-scrubbing a log word that is also a patient's name] → acceptable for diagnostics.
