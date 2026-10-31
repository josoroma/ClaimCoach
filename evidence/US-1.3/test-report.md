# Test Report: US-1.3 Thin Typed plugin_api Proxy and Error Envelope

Change: us-1-3-plugin-api-proxy
Story: US-1.3
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon); dev Python 3.12.9; Hermes gateway Python 3.11.15

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Health route proxies to a running worker: Then the response validates against the typed HealthResponse model" | PASS | `test_us_1_3_health_proxies_to_running_worker_process` → real worker process on loopback, `GET /api/plugins/claimcoach/health` → 200, `HealthResponse.model_validate_json` succeeds; `test_us_1_3_health_proxies_to_worker` (in-process worker) passed |
| 2 | "Worker unavailable returns the error envelope: Then the response body is {\"ok\": false, \"error\": {\"code\", \"message\"}} with a non-empty code" | PASS | `test_us_1_3_worker_unavailable_returns_envelope` → nothing on the port → 503, code `worker_unavailable`; `test_us_1_3_missing_token_returns_envelope` → 503 `worker_unavailable` |
| 3 | "Unhandled worker errors are mapped, not leaked: Then the response is the error envelope and contains no stack trace or document text" | PASS | `test_us_1_3_unhandled_errors_mapped` → worker route raises `RuntimeError("Jane Doe DOB 1970-01-01 MRN 0042")` → proxy 502 `worker_error`; body has no PHI, no "Traceback", no "RuntimeError" |

## Evidence Commands

```bash
make evidence STORY=US-1.3
uv run pytest tests/test_us_1_3_plugin_api.py -m "not models" -v
```

```text
tests/test_us_1_3_plugin_api.py::test_us_1_3_health_proxies_to_worker PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_health_proxies_to_running_worker_process PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_worker_unavailable_returns_envelope PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_missing_token_returns_envelope PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_unhandled_errors_mapped PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_rejected_token_maps_to_unauthorized PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_plugin_api_loads_standalone PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_plugin_api_loads_in_gateway_python PASSED
tests/test_us_1_3_plugin_api.py::test_us_1_3_token_never_goes_through_an_http_proxy PASSED
26 passed
```

Artifacts: `evidence/US-1.3/junit.xml`

## Notes

- "The desktop half calls" is exercised by an httpx client against the router mounted at
  `/api/plugins/claimcoach` (what `ctx.rest` reaches), not through a running Hermes Desktop.
  `test_us_1_3_plugin_api_loads_in_gateway_python` imports `plugin_api.py` with the Hermes
  gateway's own interpreter (Python 3.11) and dependencies, the way `web_server_dashboard.py` does.
- Fixed after independent review: httpx sends loopback traffic through `HTTP_PROXY`/`ALL_PROXY`
  by default, which would have leaked the bearer token. `WorkerClient` and the launcher now use
  `trust_env=False`. `test_us_1_3_token_never_goes_through_an_http_proxy` failed before the fix
  ("worker not healthy within 15s") and passes after it.
- `test_us_1_3_plugin_api_loads_in_gateway_python` asserts the gateway runs Python 3.11 exactly,
  as a tripwire for the 3.11 compatibility floor.
- Every error code has one fixed message (`test_us_1_3_error_codes_have_fixed_messages`), so no
  worker text reaches the UI.

## Failures

None.
