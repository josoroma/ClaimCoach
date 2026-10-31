# Tasks

## 1. Tooling configuration

- [x] 1.1 Add `pyproject.toml` (ruff, mypy strict, pytest markers, coverage fail_under 100) and lock with `uv lock`; verify `uv sync` succeeds
- [x] 1.2 Add `package.json` (pinned biome, typescript, @types/react), `biome.json`, `tsconfig.json`; verify `npm ci` succeeds
- [x] 1.3 Add `Makefile` (`help`, `install`, `check`, `verify`, `fmt`, `test`, `evidence`, `validate`, worker and plugin-link targets) and `.pre-commit-config.yaml`; verify `make help` lists targets

## 2. Harnesses

- [x] 2.1 Write `types/hermes-plugin-sdk.d.ts`; verify `test_us_1_4_plugin_js_typechecks`
- [x] 2.2 Implement `tests/fakes/fake_model_server.py` and the socket guard in `tests/conftest.py`; verify `test_us_1_4_offline_tests_use_fake_server`
- [x] 2.3 Implement `desktop/tests/fake_ctx.mjs`, the module hooks, and the fakes; verify `test_us_1_4_plugin_js_registers_contributions` and `test_us_1_4_plugin_js_allowed_imports` (node --test, 100% coverage)

## 3. Gate self-tests

- [x] 3.1 Add `test_us_1_4_make_check_passes` and `test_us_1_4_type_error_fails_gate` (marked `gate`); verify with `make verify`
- [x] 3.2 Record `evidence/US-1.4/test-report.md` and `junit.xml`
