# Proposal: US-1.1 Plugin Package Scaffold and Manifest

## Why

ClaimCoach has no code yet. Every later story needs one installable Hermes plugin folder whose
manifest Hermes Agent v0.22.5 accepts and whose Python half stays inert until the user enables it
(SPECS.md US-1.1; PRD §7, §7.1, §7.9 PC-1, PC-2, PC-5).

## What Changes

- Create the unified package under `plugin/`: `plugin.yaml` (manifest v2), `__init__.py`
  (`register(ctx)`), `skills/denial-triage/`, `dashboard/manifest.json`,
  `dashboard/plugin_api.py`, `desktop/plugin.js`, and the `claimcoach/` app package.
- Add a typed `ClaimCoachSettings` (Pydantic v2) that is the single source of truth for the
  manifest `config_schema`; a test fails when the two drift.
- Register the three `provides_tools` (`claimcoach_explain_code`, `claimcoach_payer_rules`,
  `claimcoach_case_summary`) with JSON schemas generated from Pydantic parameter models. Their
  handlers return a typed `not_implemented` error envelope until EPIC-9 delivers the behavior.
- Add `docs/runbooks/install-enable.md`.

## Capabilities

### New Capabilities
- `plugin-package`: the installable Hermes plugin folder, its v2 manifest, its settings schema,
  and the enable gate for the Python half.

### Modified Capabilities
- None.

## Impact

- New files only. No runtime dependency beyond what the Hermes gateway venv already ships
  (pydantic, fastapi, httpx).
- Code loaded by the gateway must run on the gateway's Python (3.11.15 in Hermes v0.22.5); see
  design.md.
