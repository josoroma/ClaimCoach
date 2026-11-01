# Proposal: US-12.4 Zero-Egress Check for Case Content

## Why

PRD §4 sets outbound calls carrying case content at 0 (NFR-5), and §10 limits outbound calls to
confirmed downloads and corpus imports (BR-1). Tests enforce loopback with a socket guard
(US-1.4) and a source scan pins every HTTP client and subprocess (US-7.3), but nothing proves it
of the running app: the worker, the `plugin_api` half, and the model servers it starts.

## What Changes

- New `claimcoach.egress`: `is_loopback` (shared with the test socket guard), `EgressRecord`,
  `EgressAudit` (one PEP 578 audit hook per process; `start`/`stop` switch its sink), `file_sink`,
  `read_records`.
- `python -m claimcoach.worker` starts the audit before loading the registry: every non-loopback
  `socket.connect`, `socket.sendto`, or `socket.getaddrinfo` is appended to
  `worker/egress.jsonl` (0600).
- `claimcoach.evals.flow.GatewayDriver` / `gateway_driver`: the `plugin_api` router mounted in the
  eval process over the worker client, waiting on the relay's `case.progress` events.
- `claimcoach.evals.egress_check`: preconditions (weights present for every case role, no
  download or conversion running), `lsof -nP` sampling of the worker and every model server
  (`app_processes`, `parse_lsof`, `sample_lsof`), and `run_egress_check`, which runs one case
  from upload through export and fails on any non-loopback finding.
- `python -m claimcoach.evals egress [--case ID]`, `make eval-egress`; runbook section.
- The US-7.3 pins list the two new reviewed modules (an in-process HTTP client; `lsof`).

## Capabilities

### New Capabilities
- `egress-check`: the socket audit of the worker and the measured zero-egress check of a full
  case flow.

### Modified Capabilities
- None (the worker gains the audit as part of `egress-check`).

## Impact

- The worker's audit hook runs for every audit event; it returns at once for anything but the
  three socket events and for loopback addresses.
- `worker/egress.jsonl` grows only on non-loopback attempts (confirmed downloads).
