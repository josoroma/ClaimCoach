# Test Report: US-1.2 Worker Sidecar with Per-Launch Token

Change: us-1-2-worker-sidecar
Story: US-1.2
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon); worker interpreter: project `.venv` Python 3.12.9; Node 26.13.0

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Worker binds to loopback on the first port of the range: Then it listens on 127.0.0.1:18200 and on no other interface" | PASS | `make worker-start` then `lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN` → one listener, `TCP 127.0.0.1:18200 (LISTEN)`; `test_us_1_2_worker_binds_loopback`, `test_us_1_2_default_bind_is_first_port_of_range`, `test_us_1_2_config_rejects_non_loopback_or_out_of_range` passed |
| 2 | "Worker writes a per-launch token in the plugin data dir: Then a new bearer token file exists under plugin_data_dir(\"claimcoach\") and differs from the token of the previous launch" | PASS | `stat -f '%Sp'` on `<HERMES_HOME>/plugin-data/claimcoach/worker/token` → `-rw-------`; stop + start → "tokens differ across launches: yes (43 and 43 chars)"; `test_us_1_2_worker_writes_per_launch_token`, `test_us_1_2_previous_launch_token_rejected` (a real token from the earlier launch → 401) passed |
| 3 | "Requests without the token are rejected: Then the worker responds 401 with the error envelope" | PASS | `curl` with no token, with a wrong token, on an unknown path, and with the previous launch's token → `{"ok":false,"error":{"code":"unauthorized",...}} HTTP 401`; `test_us_1_2_requests_without_token_rejected` (12 cases) passed |

## Evidence Commands

```bash
export HERMES_HOME=<scratch dir>        # keeps the real ~/.hermes untouched
make worker-start WORKER_PYTHON=$PWD/.venv/bin/python
lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN
stat -f '%Sp %N' $HERMES_HOME/plugin-data/claimcoach/worker/token
curl -s -w ' HTTP %{http_code}\n' http://127.0.0.1:18200/health
curl -s -w ' HTTP %{http_code}\n' http://127.0.0.1:18200/cases
curl -s -w ' HTTP %{http_code}\n' -H 'Authorization: Bearer wrong' http://127.0.0.1:18200/health
make worker-health
make worker-stop && make worker-start WORKER_PYTHON=$PWD/.venv/bin/python
curl -s -w ' HTTP %{http_code}\n' -H "Authorization: Bearer $T1" http://127.0.0.1:18200/health
make worker-stop && make worker-status
make evidence STORY=US-1.2
```

```text
COMMAND     PID     USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3.1 52567 josoroma    6u  IPv4 0xbb53b90650744b0d      0t0  TCP 127.0.0.1:18200 (LISTEN)
-rw------- .../demo-home/plugin-data/claimcoach/worker/token
{"ok":false,"error":{"code":"unauthorized","message":"The request is missing a valid ClaimCoach worker token."}} HTTP 401
{"ok":false,"error":{"code":"unauthorized","message":"The request is missing a valid ClaimCoach worker token."}} HTTP 401
{"ok":false,"error":{"code":"unauthorized","message":"The request is missing a valid ClaimCoach worker token."}} HTTP 401
{"ok":true,"status":"ok","version":"0.1.0"}
stopped
{"ok":false,"error":{"code":"unauthorized","message":"The request is missing a valid ClaimCoach worker token."}} HTTP 401
tokens differ across launches: yes (43 and 43 chars)
stopped
not running

Re-run after the review fixes, with HTTP_PROXY=ALL_PROXY=http://127.0.0.1:9 exported:
python3.1 60952 josoroma    6u  IPv4 0x374ac245101637f3      0t0  TCP 127.0.0.1:18200 (LISTEN)
-rw------- <scratch>/demo-home2/plugin-data/claimcoach/worker/token
-rw------- <scratch>/demo-home2/plugin-data/claimcoach/worker/worker.log
{"ok":false,"error":{"code":"unauthorized",...}} HTTP 401          (no token)
{"ok":false,"error":{"code":"not_found","message":"No such ClaimCoach route."}} HTTP 404   (valid token, unknown path)
{"ok":true,"status":"ok","version":"0.1.0"}                        (make worker-health)
stopped

tests/test_us_1_2_worker.py ..............................................
46 passed
```

Artifacts: `evidence/US-1.2/junit.xml`

## Failures

None.

## Notes

- The scenario's Given names the worker venv `~/Models/.venvs/claimcoach`. The run used the
  project's `.venv` (same Python 3.12 and dependencies) so as not to create a venv in the shared
  `~/Models` folder; `make worker-venv` creates the real one. The bind, token, and auth behavior
  does not depend on which venv runs it.
- The token lives under the profile-independent root (`<hermes root>/plugin-data/claimcoach`),
  which is `plugin_data_dir("claimcoach")` for the default profile. One worker serves every
  profile, so a named profile's gateway must find the same token (review finding; see
  design.md decision 6 and `test_us_1_3_worker_dir_is_profile_independent`).
- Fixed after independent review, each with a regression test: the worker log is created 0600 and
  records only the exception type (`test_us_1_2_unhandled_error_is_generic` asserts on the log);
  404/405/422 answer with the envelope and 422 never echoes input
  (`test_us_1_2_framework_errors_use_the_envelope`); a reused PID in a stale `worker.json` is never
  adopted or signalled (`test_us_1_2_status_never_adopts_an_unrelated_process`); a worker that
  ignores SIGTERM during a failed start is killed and its token removed
  (`test_us_1_2_start_kills_worker_that_ignores_sigterm`).
- Also verified: `stop` escalates to SIGKILL (`test_us_1_2_stop_escalates_to_sigkill`); a worker
  started by one process can be stopped by another
  (`test_us_1_2_stop_worker_started_by_another_process`).
