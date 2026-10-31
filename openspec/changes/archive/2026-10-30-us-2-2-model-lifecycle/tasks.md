# Tasks

## 1. Manager

- [x] 1.1 Add `ModelState`/`ModelStatus` to `claimcoach/models/types.py` and `claimcoach/models/manager.py` (`ModelManager.use`, `sweep_idle`, `unload`, `status`, `shutdown`, `reap_orphans`); verify `test_us_2_2_server_starts_on_first_use` against a real fake-server process
- [x] 1.2 Health check and failure handling; verify `test_us_2_2_unhealthy_server_not_used`, the port-in-use and exit-during-start tests
- [x] 1.3 Idle sweep; verify `test_us_2_2_idle_servers_unloaded` and the busy-server test

## 2. Worker

- [x] 2.1 `create_app(token, models=...)` with lifespan sweeper and shutdown; `/models/status`, `/models/{role}/load`, `/models/{role}/unload`; verify the worker route tests
- [x] 2.2 Worker `__main__` builds the registry and manager and reaps orphans; verify the serve test
- [x] 2.3 Gateway `GET /models/status` proxy and `WorkerClient.models_status`; verify the proxy test

## 3. Operations

- [x] 3.1 Makefile `models-status`, `models-load`, `models-unload`; runbook model-server sections; verify the runbook test and a live `make models-status`
- [x] 3.2 Record `evidence/US-2.2/test-report.md` and `junit.xml`
