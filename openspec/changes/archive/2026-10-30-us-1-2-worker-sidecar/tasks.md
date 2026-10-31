# Tasks

## 1. Token and app

- [x] 1.1 Implement `claimcoach/worker/token.py` (`issue_token`, `read_token`) with `secrets.token_urlsafe` and an atomic 0600 write; verify `test_us_1_2_worker_writes_per_launch_token` and the token unit tests
- [x] 1.2 Implement `claimcoach/worker/app.py` (`create_app`) with bearer middleware, `/health`, and the generic 500 handler; verify `test_us_1_2_requests_without_token_rejected` and `test_us_1_2_unhandled_error_is_generic`

## 2. Launcher

- [x] 2.1 Implement `claimcoach/worker/config.py` (`WorkerConfig`, `WorkerHandle`) and `claimcoach/worker/launcher.py` (`start_worker`, `stop_worker`, `worker_status`, CLI); verify `test_us_1_2_worker_binds_loopback` launches a real process and inspects its listening sockets
- [x] 2.2 Add `python -m claimcoach.worker` entry point; verify the serve unit test

## 3. Operations

- [x] 3.1 Add Makefile targets `worker-venv`, `worker-start`, `worker-stop`, `worker-status`; verify `make worker-status` runs
- [x] 3.2 Write `docs/runbooks/worker-start-stop-health.md`; verify the runbook lint test passes
- [x] 3.3 Record `evidence/US-1.2/test-report.md` and `junit.xml`
