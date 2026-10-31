# Proposal: US-1.4 Quality Gate and Test Harnesses

## Why

Every later story must be type-checked, linted, and tested the same way before review (SPECS.md
US-1.4; PRD ES-1, ES-2, ES-4, ES-7). Without one gate and offline harnesses, model-dependent code
would either go untested or open real network connections.

## What Changes

- `Makefile` with `check` (ruff check, ruff format --check, mypy --strict, biome check,
  tsc --noEmit --checkJs, offline pytest, node --test) plus `install`, `fmt`, `test`, `coverage`,
  `evidence`, `validate`, worker, and plugin-link targets, modeled on the legalizer Makefile
  (`help` default goal, overridable `?=` paths, exported env).
- `pyproject.toml` (uv-managed): ruff, mypy strict, pytest, coverage. **Line and branch coverage
  fail under 100%** for the app package and entry points — stricter than the 85% in ES-4, at the
  product owner's request on 2026-10-30.
- `biome.json`, `tsconfig.json` (`checkJs`), `package.json` (pinned devDependencies),
  `.pre-commit-config.yaml` (fast subset: ruff, ruff-format, biome).
- `types/hermes-plugin-sdk.d.ts` covering the SDK surface ClaimCoach uses.
- Test harnesses: `tests/fakes/fake_model_server.py` (OpenAI-compatible), a socket guard that
  fails on non-loopback connections and DNS lookups, and `desktop/tests/` with a fake `ctx`/`host`
  and module hooks that resolve the three allowed specifiers. `node --test` coverage of
  `plugin.js` also fails under 100%.

## Capabilities

### New Capabilities
- `quality-gate`: the single gate command, its checks, the offline guarantee, and the desktop
  plugin import and registration contract.

### Modified Capabilities
- None.

## Impact

- Dev-only tooling. Node devDependencies are pinned exact; Python dev deps are locked in `uv.lock`.
