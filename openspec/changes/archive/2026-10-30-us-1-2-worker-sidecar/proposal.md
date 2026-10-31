# Proposal: US-1.2 Worker Sidecar with Per-Launch Token

## Why

`plugin_api.py` runs inside the Hermes gateway (PC-4), so PDF rendering, vector search, and model
calls must run elsewhere. The PRD §7.9 worker decision puts them in an app-owned process bound to
loopback that only ClaimCoach can call (SPECS.md US-1.2).

## What Changes

- Add the worker: a FastAPI app (`claimcoach.worker.app`) served by uvicorn from the worker venv
  (`~/Models/.venvs/claimcoach`), bound to `127.0.0.1` on the first port of 18200–18219.
- Every launch writes a fresh `secrets.token_urlsafe` bearer token to
  `<hermes root>/plugin-data/claimcoach/worker/token` (profile-independent; equal to
  `plugin_data_dir("claimcoach")` for the default profile) with mode `0600`.
- Every route, including unknown paths, rejects a missing or wrong token with HTTP 401 and the
  error envelope. Unhandled exceptions become a generic 500 envelope.
- Add a launcher (`claimcoach.worker.launcher`) with typed `WorkerConfig` / `WorkerHandle` and
  `start | stop | status` commands, plus Makefile targets and
  `docs/runbooks/worker-start-stop-health.md`.

## Capabilities

### New Capabilities
- `worker-sidecar`: the loopback worker process, its per-launch token, and its auth contract.

### Modified Capabilities
- None.

## Impact

- New runtime dependency in the worker venv: `uvicorn`.
- Adds `docs/adr/0001-worker-sidecar.md` as the record of this decision (written in US-1.5).
