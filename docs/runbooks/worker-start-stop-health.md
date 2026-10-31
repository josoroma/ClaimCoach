# Runbook: Worker start, stop, and health

Story: US-1.2; US-2.2 (model servers). Decision: [ADR-0001](../adr/0001-worker-sidecar.md).
Rules: BR-11 (ports 18200–18219), BR-12, PC-6.

The worker listens on `127.0.0.1:18200` only. Each start writes a new bearer token to
`~/.hermes/plugin-data/claimcoach/worker/token` (mode `0600`); the PID file and log live next to it.

The worker owns the model servers. None starts with the worker: a role's server starts on the first
request that needs it (`127.0.0.1:18201`–`18219`, from `models.yaml`), is used only while
`GET /v1/models` answers, and stops after `idle_timeout_s` (default 600 s) without requests.
Logs: `~/.hermes/plugin-data/claimcoach/models/<port>.log` (mode `0600`).

## Preconditions

- Python 3.12 and uv: `uv --version`.
- Port 18200 free: `lsof -nP -iTCP:18200 -sTCP:LISTEN` prints nothing.
- For a non-default Hermes home or models dir, export `HERMES_HOME` / `MODELS_HOME` first.
- `make models-check` lists every role with `present` weights and `venv ok` for the roles you
  will use; otherwise follow [model-download-convert](model-download-convert.md).

## Steps

1. Create (or refresh) the worker venv at `~/Models/.venvs/claimcoach`:

   ```bash
   make worker-venv
   ```

2. Start the worker. The command waits until `/health` answers with the new token:

   ```bash
   make worker-start
   ```

3. Check the model roles (no server is running yet; every role reports `unloaded`):

   ```bash
   make models-status
   ```

4. Optional: warm a role before the biller needs it, and unload it afterwards. `models-load` waits
   until the server is healthy; it answers `model_unavailable` if the weights are missing or the
   server does not become healthy within `startup_timeout_s`, and `model_busy` if the memory guard
   kept it queued past `queue_timeout_s`:

   ```bash
   make models-load ROLE=classification
   make models-unload ROLE=classification
   ```

5. Stop the worker (SIGTERM, then SIGKILL after 30 s; removes the PID and token files). It gives
   in-flight requests 5 s, then stops every model server it started, all at once:

   ```bash
   make worker-stop
   ```

## Verification

```bash
make worker-status
make worker-health
lsof -nP -iTCP:18200 -sTCP:LISTEN
curl --noproxy '*' -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18200/health
stat -f '%Sp' ~/.hermes/plugin-data/claimcoach/worker/token
```

- `worker-status` prints the handle JSON (PID, URL, token path); exit 1 means stopped.
- `worker-health` prints `{"ok":true,"status":"ok","version":"…"}`.
- `lsof` shows exactly one listener, `127.0.0.1:18200`.
- `curl` without the token prints `401`.
- The token file is `-rw-------`.
- Through Hermes: `GET /api/plugins/claimcoach/health` returns the same body, or the envelope
  `{"ok": false, "error": {"code": "worker_unavailable", …}}` when the worker is stopped.
- `make models-status` lists every role with `state` (`unloaded`, `queued`, `starting`, `ready`,
  `unhealthy`, `stopping`), `pid`, `weights`, and `venv_present`. After `models-load`, the role is
  `ready` and `lsof -nP -iTCP:<port> -sTCP:LISTEN` shows one listener on `127.0.0.1`.
- After `make worker-stop`, `lsof -nP -iTCP:18201-18219 -sTCP:LISTEN` shows no ClaimCoach server.

## Rollback

```bash
make worker-stop
rm -rf ~/Models/.venvs/claimcoach
```

If `make worker-stop` reports `not running` but the port is still held, find and stop the owner
with `lsof -nP -iTCP:18200 -sTCP:LISTEN`, then `kill <pid>`. Logs:
`~/.hermes/plugin-data/claimcoach/worker/worker.log`.

A worker killed with SIGKILL leaves its model servers running. The next worker start stops each
process recorded in `models/servers.json` whose command line still shows the role's model path and
`--port` (this also matches `mtplx serve` after it re-executes as `python -m
mtplx.server.openai`); a PID the OS gave to another program is never signalled. If a port is still
held after that, ClaimCoach refuses to adopt it (`model_unavailable`): find the owner with
`lsof -nP -iTCP:<port> -sTCP:LISTEN` and `kill <pid>` after checking it is ClaimCoach's.
