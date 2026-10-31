# Test Report: US-1.1 Plugin Package Scaffold and Manifest

Change: us-1-1-plugin-scaffold
Story: US-1.1
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon); dev Python 3.12.9; Hermes Agent v0.22.5 (gateway Python 3.11.15); Node 26.13.0

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Manifest declares the required v2 fields: Then validation succeeds And plugin.yaml declares manifest_version 2, requires_hermes \">=0.22.5\", python_runtime external, provides_tools and config_schema" | PASS | `hermes plugins validate plugin/` → 17 checks ✓, "Validation passed." (exit 0); `test_us_1_1_hermes_validate_accepts_package`, `test_us_1_1_manifest_declares_v2_fields`, `test_us_1_1_config_schema_matches_settings` passed |
| 2 | "Backend manifest points at plugin_api.py: Then it contains name \"claimcoach\" and api \"plugin_api.py\"" | PASS | `test_us_1_1_backend_manifest_points_at_plugin_api` passed; `test_us_1_3_plugin_api_loads_standalone` imports it the way the gateway does |
| 3 | "Python half stays inert until enabled: Then no claimcoach_* tool is registered" | PASS | `test_us_1_1_python_half_inert_until_enabled` → real Hermes loader, `plugins.enabled: []` → `{"tools": [], "enabled": false, "error": "not enabled in config ..."}` |
| 4 | "Python half loads once enabled: Then the claimcoach_* tools listed in provides_tools are registered" | PASS | `test_us_1_1_python_half_loads_once_enabled` → real Hermes loader, `plugins.enabled: [claimcoach]` → `{"tools": ["claimcoach_case_summary", "claimcoach_explain_code", "claimcoach_payer_rules"], "enabled": true, "error": null}` |

## Evidence Commands

```bash
hermes plugins validate plugin/
make evidence STORY=US-1.1
```

```text
✓ manifest — plugin.yaml parses
✓ requires_hermes — spec '>=0.22.5' parses
✓ config schema — shape valid
✓ loadable — entry: __init__.py, desktop/plugin.js
✓ python dependencies — external runtime (plugin manages its own)
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ security scan — safe
✓ desktop surface — stays inside the plugin SDK surface
Validation passed.

tests/test_us_1_1_plugin_package.py ...................
19 passed
```

Probe used by criteria 3 and 4 (`tests/hermes/probe_plugins.py`, run with the Hermes venv Python
and a throwaway `HERMES_HOME` whose `plugins/claimcoach` symlinks to `plugin/`):

```text
enabled: []            → {"tools": [], "claimcoach": {"enabled": false, "tools": 0, "error": "not enabled in config (run `hermes plugins enable claimcoach` to activate)"}}
enabled: [claimcoach]  → {"tools": ["claimcoach_case_summary", "claimcoach_explain_code", "claimcoach_payer_rules"], "claimcoach": {"enabled": true, "tools": 3, "error": null}}
```

Artifacts: `evidence/US-1.1/junit.xml`

## Failures

None.

## Notes

- Criteria 3 and 4 drive `hermes_cli.plugins.discover_plugins`, the discovery entry point the
  gateway calls at startup, not a full `hermes gateway restart` of the user's own Hermes home (that
  would change the user's real configuration).
- The tools are placeholders that return the `not_implemented` envelope until US-9.1/US-9.2.
- Open question from SPECS.md (PRD §7 tree shows `specs/`, §12 names `SPECS.md`) is unchanged; the
  repo follows §12.
