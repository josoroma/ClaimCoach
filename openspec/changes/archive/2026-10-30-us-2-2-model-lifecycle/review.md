# Review: US-2.2

Change: us-2-2-model-lifecycle
Reviewer: independent general-purpose agent following `.claude/agents/story-reviewer.md` (read-only, given the changed files, not the implementer's reasoning), 2026-10-30
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | A `use()` cancelled during start or health check left the server `starting` with refcount 1, wedging the role and (via the guard) every large role (proven by probe) | `_start` stops the half-started process and leaves `unloaded` on cancel; `_acquire` releases the pin on any exception; `test_us_2_2_cancelled_start_leaves_nothing_behind`, `test_us_2_2_cancelled_health_check_releases_the_pin` |
| medium | Idle check and `stopping` were separate critical sections; a request could pin a server about to be killed (proven by probe) | One critical section in `_stop(..., only_if_idle=True)`; requests pin only once admitted; `test_us_2_2_request_never_pins_a_server_being_stopped` |
| medium | Worker SIGKILLed by the launcher (10 s) before its lifespan ran during long loads, orphaning servers; servers stopped one by one | uvicorn `timeout_graceful_shutdown=5`, concurrent stops, lifespan steps in `try/finally`, launcher waits 30 s; `test_us_2_2_worker_main_builds_models`, `test_us_2_2_lifespan_stops_servers_even_if_jobs_fail` |
| medium | Orphan reaping matched the exact argv, so `mtplx serve` (re-execs) was never reaped | Records the model path and `--port N`; `test_us_2_2_orphans_of_a_crashed_worker_are_reaped` starts orphans whose argv differs from the registry command |
| low | `terminate` never SIGKILLed group members that outlived the leader | Group SIGKILL after the leader exits, then wait until the group is empty; `test_us_2_2_group_members_are_stopped_with_the_leader`, `test_us_2_2_terminate_waits_for_the_group_to_empty` |
| low | An exception in `sweep_idle` ended the sweeper and skipped shutdown | Logged by type, sweeper continues; `test_us_2_2_sweeper_survives_a_failed_sweep` |
| low | Orphans reaped one at a time (could exceed the launcher's 15 s readiness) | SIGTERM all, one shared deadline, then SIGKILL and settle; timing asserted in the orphan test |
| info | Two stray fake servers on 18206/18207 | Leftovers of an earlier version of the orphan test; verified by command line and killed; the test now cleans up in `finally` |
| medium | (Implementer, testing) Waiters on a failed start each retried it | Waiters share the outcome of the attempt they waited on; `test_us_2_2_waiters_share_a_failed_start` |
| medium | (Implementer, live run) macOS GNU Make 3.81 ignores `.SHELLFLAGS`: piped targets exited 0 on error, and `evidence-check` only reported the last report's status | `WORKER_CURL` sets `pipefail`; the OhMyOrch loop exits on the first rejected report |

## Re-verification

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 260 pytest +
12 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all nine
stories, 2 gate self-tests). `pytest -m hermes` → 4 passed (the gateway, with the model routes,
loads in Hermes' Python 3.11). Live worker cycle with `make models-load` / `make worker-stop` →
no model server left behind.
