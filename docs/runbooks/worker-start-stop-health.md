# Runbook: Worker start, stop, and health

Story: US-1.2 (US-2.2 adds the model-server sections). Decision:
[ADR-0001](../adr/0001-worker-sidecar.md). Rules: BR-11 (ports 18200–18219), PC-6.

The worker listens on `127.0.0.1:18200` only. Each start writes a new bearer token to
`~/.hermes/plugin-data/claimcoach/worker/token` (mode `0600`); the PID file and log live next to it.

## Preconditions

- Python 3.12 and uv: `uv --version`.
- Port 18200 free: `lsof -nP -iTCP:18200 -sTCP:LISTEN` prints nothing.
- For a non-default Hermes home or models dir, export `HERMES_HOME` / `MODELS_HOME` first.

## Steps

1. Create (or refresh) the worker venv at `~/Models/.venvs/claimcoach`:

   ```bash
   make worker-venv
   ```

2. Start the worker. The command waits until `/health` answers with the new token:

   ```bash
   make worker-start
   ```

3. Stop it (SIGTERM, then SIGKILL after 10 s; removes the PID and token files):

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

## Rollback

```bash
make worker-stop
rm -rf ~/Models/.venvs/claimcoach
```

If `make worker-stop` reports `not running` but the port is still held, find and stop the owner
with `lsof -nP -iTCP:18200 -sTCP:LISTEN`, then `kill <pid>`. Logs: 
`~/.hermes/plugin-data/claimcoach/worker/worker.log`.
