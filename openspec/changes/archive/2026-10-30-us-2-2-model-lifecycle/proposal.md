# Proposal: US-2.2 Lazy Start, Health Check, and Idle Unload

## Why

Model servers hold gigabytes of unified memory. A biller should only pay for them while working:
start a role's server on first use, never use one that does not answer, and stop it when idle
(SPECS.md US-2.2, PRD §8).

## What Changes

- Add `claimcoach.models.manager.ModelManager` (async): `use(role)` starts the role's server on
  first use, waits until `GET /v1/models` answers, and yields its loopback endpoint;
  `sweep_idle()` stops servers unused for longer than `idle_timeout_s`; `unload(role)`;
  `status()`; `shutdown()`; `reap_orphans()`.
- Typed `ModelState` (`unloaded`, `queued`, `starting`, `ready`, `unhealthy`, `stopping`) and
  `ModelStatus` in `claimcoach.models.types`.
- Servers run as their own processes: fixed argv from `models.yaml`, `stdin` closed, log
  `<data>/models/<port>.log` mode 0600, `HF_HUB_OFFLINE=1`, new session. A port that is already
  taken is never adopted.
- Worker: builds the manager from `models.yaml` at start, runs the idle sweeper in its lifespan,
  stops every model server on shutdown, and adds `GET /models/status`,
  `POST /models/{role}/load`, `POST /models/{role}/unload`.
- New error codes `model_unavailable` (503) and `model_busy` (409).

## Capabilities

### New Capabilities
- `model-lifecycle`: lazy start, health check, idle unload, and status of model servers.

### Modified Capabilities
- None. Worker ownership of model servers is specified in `model-lifecycle`; the
  `worker-sidecar` requirements (loopback bind, token, auth) are unchanged.

## Impact

- `create_app(token, models=None)`: model routes exist only when a manager is passed.
- Runbook `worker-start-stop-health.md` gains model-server sections; Makefile gains
  `models-status`, `models-load`, `models-unload`.
