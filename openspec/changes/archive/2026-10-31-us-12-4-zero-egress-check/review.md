# Review: US-12.4

Change: us-12-4-zero-egress-check
Reviewer: independent `story-reviewer` agent (read-only, given the four EPIC-12 change names and the changed files, not the implementer's reasoning), 2026-10-31, with two runtime probes (a raising hook aborts `connect()`; the last sample was skipped when the flow ended mid-sample)
Verdict: pass after fixes (the check against the running app and real model servers stays UNVERIFIED: no worker runs on this Mac; model-server coverage is lsof-only and stated in the report)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The check never confirmed the worker's audit hook ran: a worker started before this change (kept by an idempotent `make start`) has none, and "no records" passed | The worker serves `GET /egress` (`EgressStatus`: `audit`, `dropped`); the check exits 2 when `audit` is false ("restart it"), and a `dropped` count that grows during the flow is a finding. A worker that cannot open `egress.jsonl` serves with the audit off. Design decision 3; `test_us_12_4_worker_without_its_audit_is_not_measured`, `test_us_12_4_cli_refuses_a_worker_without_its_audit`, `test_us_12_4_records_the_worker_could_not_write_are_a_finding`, `test_us_12_4_worker_reports_its_audit`, `test_us_12_4_worker_without_a_record_file_serves_with_the_audit_off`; runbook Preconditions say to restart the worker after an upgrade |
| medium | Model servers were sampled by leader PID only; DNS lookups (mDNSResponder, a Unix socket) and sub-sample connections are invisible; the report did not say coverage was partial | `lsof -g` samples each server's whole process group (servers start their own session); `-F pgn` attributes a child to its group. `EgressReport.observers` names what watched each process (model servers: `lsof` only). Design Risks state the gap; an in-venv audit hook is a later change. `test_us_12_4_parse_lsof`, `test_us_12_4_lsof_connection_is_caught` (a child of the worker's group) |
| low | An `OSError` writing the record (full disk) escaped the hook and broke the worker's own `connect()` | The hook catches any sink failure and counts it in `dropped`; `file_sink` creates its file up front so a folder problem shows at start. `test_us_12_4_a_failing_sink_never_breaks_the_socket_call`, `test_us_12_4_record_file_is_owner_only` |
| low | The "last sample after the flow" was skipped when the flow ended during a sample; a sampler failure surfaced only after the whole flow; other `processes()` errors escaped as tracebacks | The watcher always takes one sample after the flow; a watcher failure cancels the flow at once (its case is purged); `processes()` errors become `EgressToolError`. `test_us_12_4_one_sample_always_follows_the_flow`, `test_us_12_4_sampler_failure_stops_the_flow`, `test_us_12_4_process_lookup_failure_is_a_tool_error` |
| low | lsof exit 1 was always read as "no sockets", though lsof also exits 1 on errors | Exit 1 is accepted only with an empty stderr (a group with no sockets, or gone). `test_us_12_4_lsof_failure_is_an_error` (exit 1 with a warning), `test_us_12_4_sample_lsof_runs_lsof` (a gone group) |
| low | uvloop, if ever installed, would bypass the audit hook | The worker passes `loop="asyncio"` to uvicorn. `test_us_12_4_worker_starts_the_audit` |
| low (tests) | The CLI test sampled no process; the plugin_api test used `sys.audit` instead of a real connect | The CLI test watches this test's process group as the worker and asserts `worker:<group>` and two or more samples; the plugin_api test makes a real UDP `connect()` past the test guard (no packet is sent). `test_us_12_4_cli_writes_the_report`, `test_us_12_4_plugin_api_attempt_is_caught` |
| low (tester) | With `egress.jsonl` unreadable (mode 000) the check stopped with only `not measured: unexpected PermissionError` | `EgressLogError` names the file and what to check (exit 2). `test_us_12_4_unreadable_worker_log_is_not_measured`, `test_us_12_4_worker_log_that_cannot_be_statted_is_not_measured` |
| low (tester) | The runbook said every command exits 0/1/2, but `make` exits 2 for any failed recipe | The runbook says the 0/1/2 codes are the eval's own and shows how to read them through `make` (`Error 1` / `Error 2`, and the first line) |
| low (tester) | A corpus import running during the check is not detected | Accepted: it can only cause a false BLOCKED, never hide a leak; the runbook's Preconditions say not to run one |
| low (docs) | The design said `HF_HUB_OFFLINE` is not ours to set, but the model manager sets it | Design Risks corrected: servers run with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8232      0   1362      0   100%
=============== 1683 passed, 14 deselected in 238.59s (0:03:58) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-12.4
================ 2 passed, 1695 deselected in 241.92s (0:04:01) ================   (-m gate)
$ make evidence STORY=US-12.4
===================== 43 passed =====================
```

`make verify` ran once for the four EPIC-12 changes delivered together. The `models` tests skip
(no worker on this Mac); their rows are UNVERIFIED in `evidence/US-12.4/test-report.md`.
