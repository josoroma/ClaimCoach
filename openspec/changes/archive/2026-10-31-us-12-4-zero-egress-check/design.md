# Design: US-12.4 zero-egress check for case content

## Context

Case content flows pane → gateway (`plugin_api.py`, the `claimcoach.api.routes` router) → worker
→ model servers (BR-2), all on loopback. The worker spawns the model servers (US-2.2) and reports
their PIDs in `/models/status`. Confirmed downloads (US-2.4) are the one sanctioned way out.

## Goals / Non-Goals

Goals: one command that runs a full case flow (upload, extract, diagnose, draft, export) and
proves that the worker, the `plugin_api` code, and the model servers opened no non-loopback
connection meanwhile; a JSON report as evidence.

Non-Goals: blocking egress at runtime (a firewall's job; the audit records); watching the whole
Hermes gateway process (it legitimately talks to the agent's model provider, which carries no
case content by BR-3); DNS traffic of other apps.

## Decisions

1. **Three observers, each covering what the others cannot.** The worker's audit hook sees every
   attempt its own code makes, including failed ones and DNS lookups, before a socket exists. The
   eval process's hook does the same for the `plugin_api` router, which runs there (decision 2).
   `lsof` samples see every connection a model server (a separate program ClaimCoach does not
   instrument) or the worker holds at that moment, including a library's telemetry.
   Rejected: `lsof` alone (misses short connections between samples and failed attempts); a
   packet capture (needs root).
2. **The flow runs through the `plugin_api` router mounted in the eval process.** The router is
   the code Hermes loads from `plugin_api.py`; mounting it in-process with its dependencies
   pointed at the worker client and an event sink lets the eval's hook watch exactly that code,
   and the flow waits on `case.progress` events as the pane does. Rejected: lsof on the Hermes
   gateway (its other connections are not ClaimCoach's and would fail the check falsely).
3. **The audit is always on in the worker, idle elsewhere, and the check refuses a worker that is
   not recording.** A PEP 578 hook cannot be removed, so `EgressAudit` installs one per process
   and switches its sink; the worker starts it before the registry loads, so its whole life is
   recorded, and serves on the stdlib event loop (`loop="asyncio"`: uvloop's sockets raise no
   audit events). `GET /egress` answers whether the hook records and how many attempts it could
   not write (`dropped`); the check exits 2 for a worker whose audit is off (one started before
   this change: restart it), and a `dropped` count that grows during the flow is a finding. The
   hook never raises into the socket call it observes. A record holds time, process, PID, event, host,
   port: no payload (BR-14). The check reads only records appended after it started (a byte
   offset), so a past confirmed download does not fail it.
4. **Preconditions make the Gherkin's Given checkable.** The check refuses (exit 2) when any case
   role lacks weights or any role is downloading or converting; nothing else in the app may reach
   out. A corpus import is a request the operator would be running at the same time; the runbook
   says not to.
5. **An unparseable `lsof` remote, or a torn audit line, counts as a finding.** The check fails
   closed: an observation it cannot read is never treated as loopback.

## Risks / Trade-offs

- [A model server is watched by `lsof` only: a connection it opens and closes between two
  samples, or a DNS lookup (macOS resolves through mDNSResponder over a Unix socket), is not
  seen] → `lsof -g` samples each server's whole process group (it starts its own session, so
  forked helpers count) every 0.5 s and once more after the flow; the model manager starts every
  server with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; the report's `observers` names what
  watched each process, so the partial coverage is stated, not implied. An audit hook inside the
  servers' venvs (a `sitecustomize`) is a later change.
- [A sampling failure] → stops the flow at once and the check exits 2.
- [The audit hook adds work to every audit event in the worker] → a dict lookup and return for
  non-socket events; loopback returns before any object is built.
