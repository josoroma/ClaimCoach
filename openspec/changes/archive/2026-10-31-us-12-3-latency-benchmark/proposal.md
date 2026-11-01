# Proposal: US-12.3 Upload-to-Draft Latency Measurement

## Why

PRD §4 targets a median ≤ 10 minutes from denial upload to appeal-ready draft on the M3 Pro
(NFR-3). Nothing measures it: each job has a deadline, but no one times the flow a biller sees.

## What Changes

- `claimcoach.evals.latency`: each benchmark case runs from its first upload to the finished
  draft through the worker's REST API (`run_case(..., until="draft")`), timed per step (upload,
  extract, diagnose, draft); `LatencyReport` holds every case and the median; the gate fails when
  the median exceeds 600 s or any case failed.
- `benchmark_cases`: the US-12.2 denial set, taken round-robin by document kind.
- `python -m claimcoach.evals latency [--limit N]`, `make eval-latency [LIMIT=n]`; runbook section.

## Capabilities

### New Capabilities
- `latency-benchmark`: the upload-to-draft benchmark and its median gate.

### Modified Capabilities
- None.

## Impact

- A full run with real models takes the set's size times the flow time (20 cases; minutes each);
  `LIMIT` shortens it. Cases run one at a time so the memory guard loads models in sequence
  (BR-12). Each case is purged afterwards.
