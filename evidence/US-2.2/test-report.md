# Test Report: US-2.2 Lazy Start, Health Check, and Idle Unload

Change: us-2-2-model-lifecycle
Story: US-2.2
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`, also the worker interpreter); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "A role's server starts on first use: Then the worker starts the configured server and serves the request once /v1/models reports healthy" | PASS | `test_us_2_2_server_starts_on_first_use`: nothing listens on the classification port and every role is `unloaded`; the first `use(classification)` spawns the configured command (`ps` shows `--host 127.0.0.1 --port <port>`), returns only once `/v1/models` answers, and a chat completion through the endpoint returns 200; live `make models-load ROLE=classification` → `ready`, `lsof` shows one listener on `127.0.0.1:18202`. `test_us_2_2_shared_server_started_once`, `test_us_2_2_concurrent_first_use_starts_one_server` (3 concurrent requests → 1 process) |
| 2 | "An unhealthy server is not used: Then the request fails with the error envelope and the model status reports unhealthy" | PASS | `test_us_2_2_unhealthy_server_not_used`: a server whose `/v1/models` answers 503 → `ModelUnavailableError`; `POST /models/classification/load` → 503 `{"ok": false, "error": {"code": "model_unavailable", …}}`; `GET /models/status` → `unhealthy`, no PID, port closed. Also `test_us_2_2_ready_server_failing_health_is_replaced`, `test_us_2_2_port_taken_by_another_process` (foreign server never adopted or signalled), `test_us_2_2_server_that_cannot_start[2]`, `test_us_2_2_health_requires_an_openai_model_list[4]` |
| 3 | "Idle servers are unloaded: Then the server process is stopped and the model status reports unloaded" | PASS | `test_us_2_2_idle_servers_unloaded` (injected clock): at 599 s of 600 the sweep keeps the server; at 601 s it returns the port, the PID is gone, status `unloaded`; `test_us_2_2_busy_servers_kept`; `test_us_2_2_sweeper_runs_in_the_background` (lifespan sweeper unloads on its own); `test_us_2_2_sweep_rechecks_before_stopping` |

## Evidence Commands

```bash
make evidence STORY=US-2.2
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/Models   # models.yaml → fake servers
make models-check
make worker-start WORKER_PYTHON=$PWD/.venv/bin/python
make models-status
make models-load ROLE=classification
lsof -nP -iTCP:18202 -sTCP:LISTEN
make models-load ROLE=explanation; echo "rc=$?"     # weights deleted for this role
make models-unload ROLE=classification
make models-load ROLE=phi_detection && make worker-stop
lsof -nP -iTCP:18202 -sTCP:LISTEN
stat -f '%Sp %N' $HERMES_HOME/plugin-data/claimcoach/models/*
```

```text
===================== 36 passed, 227 deselected in 29.06s ======================

== models-status (before)
classification unloaded present   ... explanation unloaded missing ... (all 8 roles unloaded)
== models-load classification
classification ready pid 78698 port 18202
python3.1 78698 josoroma    6u  IPv4 ...  TCP 127.0.0.1:18202 (LISTEN)
== models-load explanation (weights missing)
{"ok": false, "error": {"code": "model_unavailable",
 "message": "The local model for this step is missing or not responding."}}
rc=2
== models-unload classification
classification unloaded None
== load phi_detection then worker-stop
phi_detection ready pid 78737
stopped
listeners on 18202 after stop: (none)
-rw------- .../models/18202.log
-rw------- .../models/servers.json
```

Artifacts: `evidence/US-2.2/junit.xml`

## Failures

None.

## Notes

- The servers in the tests and the live run are real processes started from `models.yaml`
  (`python -m tests.fakes.fake_model_server`, an OpenAI-compatible server), on real loopback
  ports. The shipped commands for the real runtimes (`mlx_lm.server`, `mlx_vlm.server`,
  `mtplx serve`) were not started: `test_us_2_2_real_drafting_server_starts_and_unloads`
  (`@pytest.mark.models`) is written but not run, because another app had its own Bonsai 27B
  `mtplx serve` running on :8080 and loading a second 27B would have created the memory pressure
  this epic guards against. Run it with `uv run pytest -m models -k us_2_2` when no other 27B is
  loaded.
- Open question resolved: default idle timeout 600 s (design.md of US-2.1, decision 9), editable
  in `models.yaml`.
- Found while testing and fixed: concurrent requests waiting on a start that failed each retried
  the start (one bad server cost N timeouts); `test_us_2_2_waiters_share_a_failed_start` now
  asserts a single spawn.
- Found during the live run and fixed: macOS GNU Make 3.81 ignores `.SHELLFLAGS`, so a 503 piped
  through `json.tool` exited 0; the model targets now set `pipefail` themselves (rc=2 above).
- Fixed after independent review (see `openspec/changes/us-2-2-model-lifecycle/review.md`),
  each with a regression test: a cancelled start no longer wedges the role or the memory guard
  (`test_us_2_2_cancelled_start_leaves_nothing_behind`,
  `test_us_2_2_cancelled_health_check_releases_the_pin`); a request can no longer pin a server
  being stopped (`test_us_2_2_request_never_pins_a_server_being_stopped`); worker shutdown fits the
  launcher's budget (`test_us_2_2_worker_main_builds_models`,
  `test_us_2_2_lifespan_stops_servers_even_if_jobs_fail`); process-group stragglers are killed
  (`test_us_2_2_group_members_are_stopped_with_the_leader`,
  `test_us_2_2_terminate_waits_for_the_group_to_empty`); the sweeper survives a failed sweep; orphans
  are matched by model path and port (covers `mtplx serve` re-executing itself) and share one
  deadline.
- Post-review live cycle with the same scratch setup: `make models-load ROLE=classification` →
  `ready`, `servers.json` = `{"18202": {"pid": 91880, "markers": ["…/Models/Qwen3-8B-4bit",
  "--port 18202"]}}`; `make worker-stop` → `stopped` in 0.7 s, no listener left on 18202.
- Servers run with `HF_HUB_OFFLINE=1` (`test_us_2_2_server_runs_offline_with_private_log`), logs
  and `servers.json` are 0600, and a worker killed with SIGKILL has its servers reaped on the next
  start (`test_us_2_2_orphans_of_a_crashed_worker_are_reaped[sigterm|sigkill]`); a stranger PID
  is never signalled.
