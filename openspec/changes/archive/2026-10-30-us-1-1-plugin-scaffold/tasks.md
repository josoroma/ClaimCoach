# Tasks

## 1. Package tree

- [x] 1.1 Create `plugin/` per PRD §7 (`plugin.yaml`, `__init__.py`, `_bootstrap.py`, `skills/denial-triage/SKILL.md`, `dashboard/manifest.json`, `dashboard/plugin_api.py`, `desktop/plugin.js`, `claimcoach/`) with module docstrings citing US-1.1; verify with `hermes plugins validate plugin/`
- [x] 1.2 Implement `_bootstrap.ensure_app_package()`; verify `test_us_1_1_bootstrap_*` covers fresh load, reuse, and collision

## 2. Settings and tools

- [x] 2.1 Define `ClaimCoachSettings` (Pydantic v2) and `config_schema()`; mirror it in `plugin.yaml`; verify `test_us_1_1_config_schema_matches_settings`
- [x] 2.2 Define tool parameter models and register the three `provides_tools` with generated schemas and `not_implemented` handlers; verify `test_us_1_1_tools_*`

## 3. Acceptance tests and docs

- [x] 3.1 Add `test_us_1_1_manifest_declares_v2_fields`, `test_us_1_1_backend_manifest_points_at_plugin_api`, `test_us_1_1_python_half_inert_until_enabled`, `test_us_1_1_python_half_loads_once_enabled` (the last two drive the real Hermes loader); verify they pass
- [x] 3.2 Write `docs/runbooks/install-enable.md` (Preconditions, Steps, Verification, Rollback); verify the runbook lint test passes
- [x] 3.3 Record `evidence/US-1.1/test-report.md` and `evidence/US-1.1/junit.xml`; verify the report passes the evidence contract check
