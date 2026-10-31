# ADR-0001: Run heavy work in an app-owned worker sidecar

- Status: Accepted
- Date: 2026-10-30
- Deciders: Product Manager (PRD §7.9), engineering
- Implements: US-1.2, US-1.3

## Context

ClaimCoach ships as one Hermes plugin package (PRD §7). Its backend half, `dashboard/plugin_api.py`,
is imported into the **Hermes gateway process** (PC-4) and runs on the gateway's interpreter
(Python 3.11.15 in Hermes v0.22.5) with the gateway's dependencies. The package declares
`python_runtime: external` (PC-5), so Hermes installs nothing for it.

The product needs PDF rasterization, vector search, and calls to local MLX model servers that hold
8B–27B models (PRD §8). Running that inside the gateway would:

- block or crash the process every Hermes profile and chat depends on;
- force ClaimCoach's dependencies into the gateway venv, which Hermes owns and upgrades;
- couple ClaimCoach's memory use to the gateway's lifetime.

## Decision

Heavy work runs in an **app-owned worker process**:

- its own venv at `~/Models/.venvs/claimcoach` (Python 3.12);
- bound to `127.0.0.1:18200`, the first port of ClaimCoach's range 18200–18219 (BR-11), and to no
  other interface; the bind host is a type-level constant;
- every launch writes a new `secrets.token_urlsafe(32)` bearer token to
  `<hermes root>/plugin-data/claimcoach/worker/token` with mode `0600` (the profile-independent
  root: one worker serves every profile; for the default profile this is
  `plugin_data_dir("claimcoach")`); every worker route, including unknown paths, rejects a missing
  or wrong token with 401 and the error envelope;
- every other failure is also the envelope, and the worker logs only the exception type, never its
  message;
- `plugin_api.py` and the agent tools are thin typed proxies (`WorkerClient`) that read the current
  token per request, ignore proxy environment variables, and map every failure to
  `{"ok": false, "error": {"code", "message"}}` with fixed, PHI-free messages;
- the worker launches and stops the model servers (EPIC-2).

## Consequences

- The gateway stays light, and ClaimCoach controls its own dependency versions.
- Code imported by the gateway (`plugin/__init__.py`, `dashboard/plugin_api.py`, and the
  `claimcoach.api`, `claimcoach.agent`, `claimcoach.settings`, `claimcoach.worker.config` modules) must
  stay compatible with Python 3.11 and import nothing beyond pydantic, fastapi, and httpx. Ruff and
  mypy target 3.11 to enforce this.
- The worker is one more process to operate:
  [worker-start-stop-health](../runbooks/worker-start-stop-health.md) covers it. Until US-2.2 adds
  lazy start, someone starts it explicitly (`make worker-start`).
- Any local process running as the same macOS user can read the 0600 token. That is the same trust
  boundary as the user's Hermes home; a token per launch limits how long a leaked token stays
  valid.
- Another process on 18200 blocks the worker; `start` fails with a clear error and the
  troubleshooting runbook shows how to find the owner.

## Alternatives considered

- **Run everything in `plugin_api.py`.** Rejected for the reasons in Context.
- **Hermes plugin host isolation (`plugins.isolation: host`).** It isolates the agent half but still
  uses the shared interpreter and buffers dashboard responses; it does not give ClaimCoach its own
  venv or model-process lifecycle.
- **Unix domain socket instead of TCP.** Avoids port collisions, but uvicorn/httpx loopback TCP is
  simpler to inspect (`lsof`, `curl`) and matches the model servers' port range. Revisit if port
  collisions become common.
- **Pass the token through an environment variable.** Rejected: visible in `ps eww` to the same user
  and kept in crash reports.
