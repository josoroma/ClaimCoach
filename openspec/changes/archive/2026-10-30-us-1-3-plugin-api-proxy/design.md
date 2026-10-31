# Design: US-1.3 Thin Typed plugin_api Proxy and Error Envelope

## Context

See proposal.md. The worker token file changes on every launch (US-1.2), so the proxy must read it
per request rather than cache it at import time.

## Decisions

1. **Envelope codes are a closed set** (`ErrorCode` `Literal`): `invalid_request`,
   `unauthorized`, `worker_unavailable`, `worker_error`, `invalid_worker_response`,
   `not_implemented`, `internal_error`. The desktop half can switch on them; each code has one
   fixed message, so no worker text reaches the UI or logs.
2. **Status mapping.** Worker unreachable, timed out, or token missing → 503
   `worker_unavailable`. Worker 401 → 401 `unauthorized`. Any other worker error status → 502
   `worker_error`. Worker 2xx with a body that fails validation → 502 `invalid_worker_response`.
   The worker's body is never forwarded. *Alternative:* forward the worker's envelope code for
   4xx — rejected until a route needs it; one rule (never forward worker output) is easier to
   audit.
3. **Dependency-injected client.** `get_worker_client()` is a FastAPI dependency, so tests swap in
   a client backed by `httpx.ASGITransport(worker_app)` with no sockets.
4. **`token_provider` callable** instead of a token string, so the per-launch token is read at
   request time.

## Risks / Trade-offs

- [Fixed messages hide detail while debugging] → the worker log keeps the detail; the runbook says
  where to look.
