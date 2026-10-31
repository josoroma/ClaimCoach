# Tasks

## 1. Models and client

- [x] 1.1 Implement `claimcoach/api/models.py` (`ApiError`, `ErrorEnvelope`, `HealthResponse`, `ErrorCode`); verify model unit tests
- [x] 1.2 Implement `claimcoach/api/client.py` `WorkerClient` with typed errors and no bare `except`; verify client unit tests cover connect failure, missing token, 4xx envelope, 5xx, and invalid body

## 2. Router

- [x] 2.1 Implement `claimcoach/api/routes.py` (`router`, `get_worker_client`) and re-export `router` from `dashboard/plugin_api.py`; verify `test_us_1_3_health_proxies_to_worker`, `test_us_1_3_worker_unavailable_returns_envelope`, `test_us_1_3_unhandled_errors_mapped`
- [x] 2.2 Verify `plugin_api.py` loads the way the gateway loads it (standalone module) in `test_us_1_3_plugin_api_loads_standalone`

## 3. Evidence

- [x] 3.1 Record `evidence/US-1.3/test-report.md` and `junit.xml`
