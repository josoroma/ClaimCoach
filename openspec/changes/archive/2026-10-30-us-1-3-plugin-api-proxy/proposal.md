# Proposal: US-1.3 Thin Typed plugin_api Proxy and Error Envelope

## Why

The desktop half reaches ClaimCoach only through `ctx.rest` → `plugin_api.py` (PC-2, PC-4), and
`plugin_api.py` must stay a thin proxy to the worker so the gateway never runs heavy work. The
desktop needs predictable bodies: a typed success model or the error envelope (SPECS.md US-1.3,
ES-8).

## What Changes

- Add `claimcoach/api/models.py` with `ApiError`, `ErrorEnvelope`, `HealthResponse`, and the
  stable error codes.
- Add one httpx-based `WorkerClient` with typed methods. It catches `httpx.HTTPError` and
  `pydantic.ValidationError` explicitly and raises typed `WorkerError` subclasses; no bare
  `except`.
- `dashboard/plugin_api.py` exports `router` with `GET /health`, which proxies to the worker and
  maps every failure to the envelope.

## Capabilities

### New Capabilities
- `plugin-api-proxy`: the `/api/plugins/claimcoach/*` contract seen by the desktop half,
  including the error envelope and how worker failures map onto it.

### Modified Capabilities
- None.

## Impact

- Runs inside the gateway on Python 3.11 with the gateway's fastapi/httpx/pydantic.
- Later stories add routes to `claimcoach/api/routes.py` and methods to `WorkerClient`.
