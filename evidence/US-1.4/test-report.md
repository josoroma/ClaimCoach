# Test Report: US-1.4 Quality Gate and Test Harnesses

Change: us-1-4-quality-gate
Story: US-1.4
Verdict: pass
Coverage: 6/6 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon); Python 3.12.9 (uv); Node 26.13.0; ruff 0.17.3; mypy 2.4.1; biome 2.6.4; TypeScript 7.0.2

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "make check passes on a clean tree: Then ruff check, ruff format --check, mypy --strict, biome check, tsc --noEmit --checkJs, and offline pytest all run and the command exits 0" | PASS | `make check` → exit 0; `test_us_1_4_make_check_passes` (gate) asserts every tool ran and both coverage reports hit 100% |
| 2 | "A type error fails the gate: Then the command exits non-zero and names the mypy error" | PASS | `make check MYPY_EXTRA=gate_demo_bad.py` → exit 2, `gate_demo_bad.py:2: error: Incompatible return value type (got "str", expected "int")  [return-value]`; `test_us_1_4_type_error_fails_gate` (gate) passed |
| 3 | "plugin.js is type-checked against the SDK stub: Then it reports zero errors" | PASS | `npm exec -- tsc --noEmit -p tsconfig.json` → no output, exit 0; `test_us_1_4_plugin_js_typechecks` passed |
| 4 | "plugin.js registers its contributions against a fake ctx: Then the expected pane, route, statusbar, and settings contributions are recorded" | PASS | `node --test` → `test_us_1_4_plugin_js_registers_contributions` ✔ (pane `case-pane`, route `/claimcoach/dashboard`, nav, `statusbar.right` `local-only`, settings page `settings`) |
| 5 | "plugin.js imports only allowed specifiers: Then every import specifier is one of @hermes/plugin-sdk, react, or react/jsx-runtime" | PASS | `node --test` → `test_us_1_4_plugin_js_allowed_imports` ✔ |
| 6 | "Offline tests use the fake model server: Then no test opens a network connection to a non-loopback address" | PASS | `test_us_1_4_offline_tests_use_fake_server` (fake server on `127.0.0.1`), `test_us_1_4_socket_guard_blocks_non_loopback` (`10.255.255.1`, `93.184.216.34`, DNS for `example.com` all raise `NetworkBlockedError`); the guard is autouse for every offline test |

## Evidence Commands

```bash
make check
make check MYPY_EXTRA=<scratch>/gate_demo_bad.py
make verify
make evidence STORY=US-1.4
```

```text
uv run ruff check .                     → All checks passed!
uv run ruff format --check .            → 48 files already formatted
npm exec --no -- biome check .          → Checked 11 files. No fixes applied.
uv run mypy plugin/claimcoach tests tools → Success: no issues found in 28 source files
uv run mypy --no-explicit-package-bases plugin/__init__.py plugin/_bootstrap.py plugin/dashboard/plugin_api.py → Success: no issues found in 3 source files
npm exec --no -- tsc --noEmit -p tsconfig.json → (no output)
uv run pytest -m "not models and not gate" --cov → TOTAL 484 stmts, 52 branches, 100%
  Required test coverage of 100.0% reached. Total coverage: 100.00%
  133 passed, 2 deselected
npm test → tests 12, pass 12, fail 0; plugin.js | 100.00 | 100.00 | 100.00
make check exit 0

make check MYPY_EXTRA=.../gate_demo_bad.py
.../gate_demo_bad.py:2: error: Incompatible return value type (got "str", expected "int")  [return-value]
Found 1 error in 1 file (checked 29 source files)
make: *** [typecheck] Error 1
make check exit 2

uv run pytest -m gate → 2 passed
```

Artifacts: `evidence/US-1.4/junit.xml`, `evidence/US-1.4/junit-node.xml`

## Failures

None.

## Notes

- Coverage threshold is 100% (line and branch for Python, line/branch/function for plugin.js),
  stricter than the 85% in ES-4, at the product owner's request. Worker child processes are
  measured too (`coverage patch = subprocess`, `sigterm = true`), and
  `test_us_1_4_no_coverage_exclusions` forbids `pragma: no cover` and equivalents.
- The 2 deselected are the `gate` tests, run by `make verify` (and included in
  `make evidence STORY=US-1.4`: 17 passed).
- Scope of criterion 6: the socket guard covers the pytest process. Child processes the suite
  starts (the worker, `hermes plugins validate`, the Hermes loader probe) are not guarded; the
  worker only listens on loopback and the Hermes subprocesses are the user's installed Hermes.
  Process-wide egress auditing is US-12.4.
- `.pre-commit-config.yaml` runs the fast subset (ruff, ruff format, biome) with the pinned local
  tools; `make install` installs the hook.
