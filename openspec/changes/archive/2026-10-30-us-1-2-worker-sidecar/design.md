# Design: US-1.2 Worker Sidecar with Per-Launch Token

## Context

See proposal.md. The worker does not import Hermes: it runs in its own venv, so the plugin data
dir is passed in by whoever launches it. In the gateway that path comes from
`plugins.plugin_storage.plugin_data_dir("claimcoach")`.

## Goals / Non-Goals

**Goals:** loopback-only bind enforced by the type system; a token that changes every launch;
one auth check in front of every route; a launcher the runbook and later stories (US-2.2 lazy
start) can call.

**Non-Goals:** automatic worker start from the gateway (US-2.2), model servers (EPIC-2),
structured JSON logging (US-3.4).

## Decisions

1. **The worker issues its own token at startup.** Whoever starts the process (launcher, runbook,
   a future supervisor), the token is new. The file is written to a temp name created with
   `os.open(..., 0o600)` and moved with `os.replace`, so a reader never sees a partial token and
   the mode is never wider than `0600`. *Alternative:* launcher passes the token through env —
   rejected, env is visible in `ps eww` to the same user and survives in crash reports.
2. **`host` is `Literal["127.0.0.1"]` and `port` is bounded to 18200–18219** in `WorkerConfig`, so
   a misconfiguration fails validation instead of binding `0.0.0.0` (BR-11).
3. **Auth is middleware, not a dependency.** Middleware runs before routing, so unknown paths and
   future routes return 401 without each handler opting in. Comparison uses
   `secrets.compare_digest`.
4. **Launcher waits on the new token, then on `/health`.** It deletes the previous token before
   spawning so it can never authenticate with a stale one, and stops the process if readiness
   times out.
5. **PID file next to the token** (`worker/worker.json`, the serialized `WorkerHandle`) lets
   `stop`/`status` work across shells. A PID is trusted only if `ps -o command=` shows
   `-m claimcoach.worker` (or it is a child this process spawned and still holds), so a PID reused
   after a crash or reboot is never adopted or signalled.
6. **Worker state is app-level.** One worker on one port serves every profile, so its token lives
   under the profile-independent root (`hermes_constants.get_default_hermes_root()` in the
   gateway; `HERMES_HOME`, or its root when it names a profile, elsewhere). Case data (EPIC-4)
   stays in the per-profile `plugin_data_dir`.
7. **The worker catches every exception at its outermost middleware** and logs only type, method,
   and path. Letting it reach Starlette's `ServerErrorMiddleware` would write the traceback and
   message (possibly document text) to `worker.log`. 404/405/422 also answer with the envelope;
   FastAPI's default 422 body echoes the rejected input.
8. **Loopback calls ignore proxy environment variables** (`trust_env=False`). httpx does not
   bypass proxies for 127.0.0.1, so `HTTP_PROXY`/`ALL_PROXY` would otherwise receive the token.

## Risks / Trade-offs

- [Port 18200 already in use] → `start` fails with a clear error naming the port; the runbook's
  Troubleshooting step shows `lsof -nP -iTCP:18200`.
- [Stale PID file after a crash] → `status` checks the PID is a live ClaimCoach worker and
  removes the PID file otherwise.
- [uvicorn's own startup/shutdown logging] → carries no request data; structured JSON logging
  with request IDs is US-3.4's scope.
