# Design: US-2.2 Lazy Start, Health Check, and Idle Unload

## Context

The worker (US-1.2) is one asyncio process. Model servers are OpenAI-compatible HTTP servers
(`mlx_lm.server`, `mlx_vlm.server`, `mtplx serve`) that take tens of seconds to load. Roles that
share a port share one server (US-2.1 decision 2).

## Goals / Non-Goals

**Goals:** a role's server starts on first use only; a server that fails `/v1/models` is never
handed to a caller; idle servers stop; every wait is bounded; the worker never leaves or adopts
stray processes.

**Non-Goals:** residency rules between servers (US-2.3 plugs into the same admission step); model
downloads (US-2.4); the inference client each feature uses (EPIC-5/6/7).

## Decisions

1. **One `asyncio.Condition` guards all server state.** `use(role)` pins the server
   (`refcount += 1`), then admits it: a `ready` server is health-checked, an `unloaded` or
   `unhealthy` one is started by exactly one task while others wait on the condition. Pinned
   servers are never swept or evicted. *Alternative:* a lock per server — rejected, US-2.3 needs
   to see every server at once.
2. **Health = `GET /v1/models` → 200 with a `data` list**, polled every 0.25 s until
   `startup_timeout_s`, and checked again on every `use()` of a ready server. Failure stops the
   process and marks the server `unhealthy`; the caller gets `ModelUnavailableError` →
   `model_unavailable` envelope. The next request retries the start. Calls use
   `trust_env=False`.
3. **Waiters on a failed start fail too.** A task that waited for another task's start does not
   start a second attempt itself; it raises, so one bad server costs one timeout, not N.
4. **Idle sweep** runs every `min(30 s, idle_timeout_s / 4)` in the worker lifespan; it stops
   servers whose refcount is 0 and whose last use is older than `idle_timeout_s` (default 600 s).
   The clock is injectable for tests.
5. **Stop = SIGTERM to the process group, SIGKILL after 10 s.** Servers start in a new session,
   so a server's own children stop with it.
6. **Never adopt a port.** Before starting, the manager probes `127.0.0.1:<port>`; if anything
   answers, the start fails (`model_unavailable`) rather than trusting an unknown process.
7. **Orphan reaping.** The manager records `{port: {pid, markers}}` in
   `<data>/models/servers.json`, where the markers are the model path and the `--port N` pair. On
   worker start it SIGTERMs every recorded PID whose `ps -o command=` still contains both markers,
   waits for all of them under one `term_grace` deadline, SIGKILLs the rest, then clears the file.
   Markers rather than the exact argv, because `mtplx serve` re-executes itself as
   `python -m mtplx.server.openai` (found in review).
9. **Cancellation leaves no state behind** (review finding, high). A `use()` cancelled while its
   server starts stops the half-started process and leaves the role `unloaded`; one cancelled
   during a health check releases its pin. Otherwise a caller's timeout would wedge the role and,
   through the memory guard, every other large role.
10. **The idle check and the switch to `stopping` are one critical section** (review finding), so
    a request can never pin a server that is about to be killed. A waiting request does not pin
    the server either; it pins only once admitted.
11. **Shutdown budget.** uvicorn drains requests for 5 s (`timeout_graceful_shutdown`), cancels the
    rest (decision 9 cleans up), then the lifespan stops jobs and servers concurrently, each step in
    its own `try/finally`; the launcher waits 30 s before SIGKILL. A failed idle sweep is logged by
    type and the sweeper keeps running. Group members that outlive a server's main process are
    SIGKILLed with its process group.
8. **Model routes are opt-in on `create_app`.** Without a manager the routes do not exist (404
   envelope), so US-1.x tests and tools that only need `/health` stay unchanged.

## Risks / Trade-offs

- [A model that needs longer than 300 s to load] → `startup_timeout_s` is per role in
  `models.yaml`.
- [Model servers have no auth on loopback] → same exposure as running `mlx_lm.server` by hand;
  they hold no state, and BR-2 keeps PHI in requests from the worker only. `mtplx serve` runs with
  `--no-auth` for the same reason.
- [Worker killed with SIGKILL] → servers outlive it; decision 7 reaps them on the next start, and
  the troubleshooting runbook covers the manual case.
