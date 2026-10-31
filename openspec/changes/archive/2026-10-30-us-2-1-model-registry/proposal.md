# Proposal: US-2.1 Model Role Registry in models.yaml

## Why

Every later epic calls a local model by *role* (extraction, PHI detection, drafting, …). ClaimCoach
must reuse the weights already in `~/Models` without copying them and must never collide with
other apps' servers, so one typed file has to say, per role, which directory, venv, command, and
port to use (SPECS.md US-2.1, PRD §8, BR-11).

## What Changes

- Add `claimcoach.models.types` with the `ModelRole` enum (the eight PRD roles), importable by the
  gateway without YAML or process code.
- Add `claimcoach.models.registry` with `ModelSpec`, `ConversionSpec`, `ResidencyPolicy`,
  `AcquireCommands`, and `ModelRegistry` (Pydantic v2, `extra="forbid"`), plus `models_home()`
  and `ensure_registry_file()`.
- Ship `claimcoach/models/models.default.yaml`; the worker writes it to
  `<app data dir>/models.yaml` on first run and never overwrites an edited copy.
- Validation: every role present; model and source directories relative to `MODELS_HOME` with no
  `..`; ports inside 18200–18219, 18200 reserved for the worker; roles may share a port only when
  they describe the same server; every serving command binds `{host}` and `{port}` and uses only
  known placeholders. Errors name the entry, e.g.
  `roles.classification.port: port 18300 is outside the allowed range 18200-18219`.
- `python -m claimcoach.models init|check` and `make models-init` / `make models-check`.

## Capabilities

### New Capabilities
- `model-registry`: the typed per-role model registry and its default file.

### Modified Capabilities
- None.

## Impact

- `pyyaml` moves from a dev dependency to a runtime dependency (the worker parses `models.yaml`).
- No network access, no weight files touched: the registry only resolves paths.
