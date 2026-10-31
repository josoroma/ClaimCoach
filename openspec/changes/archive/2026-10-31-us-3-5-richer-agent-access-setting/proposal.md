# Proposal: US-3.5 Richer Agent Access When the Hermes Model Is Local (setting only)

## Why

PRD §7.2 allows a setting for richer agent access when the user's Hermes model is local, off by
default and shown in the statusbar. SPECS.md marks the story NEEDS CLARIFICATION: what "richer"
allows, and how a local model is detected, are open. The two acceptance scenarios (off by
default; statusbar shows it) can be delivered without deciding either, as long as the setting
grants nothing yet.

## What Changes

- `ClaimCoachSettings.richer_agent_access: bool = False`, rendered into `plugin.yaml`
  `config_schema` (the existing drift test keeps them equal).
- `load_settings()` reads `plugins.entries.claimcoach.settings` through Hermes'
  `load_config_readonly()`; missing, unreadable, or invalid values read as the defaults (off).
- Gateway `GET /settings` → `SettingsResponse{ok, richer_agent_access}`.
- Statusbar item: `Local-only`, or `Local-only · richer agent access on` with a tooltip saying
  agent tool results are still redacted.
- No code path changes redaction based on the setting (a test lists the only files that read it).

## Capabilities

### New Capabilities
- `richer-agent-access`: the opt-in setting and its statusbar display.

### Modified Capabilities
- None.

## Impact

- Settings → Plugins shows a new checkbox. The open questions stay open in SPECS.md; the
  behavior behind the setting is a follow-up once the Product Manager decides it.
