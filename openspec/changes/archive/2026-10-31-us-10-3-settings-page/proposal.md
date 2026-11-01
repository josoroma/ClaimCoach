# Proposal: US-10.3 Settings Page for Models, Corpus, and Retention

## Why

PRD §7: a settings page for models, corpus, and retention. US-1.4 registers a ClaimCoach settings
page (feature-detected) that shows only the worker status; Hermes' generic Settings → Plugins form
edits the values but shows no model or corpus status, and the biller has no single place to see how
ClaimCoach runs and change the retention period.

## What Changes

- Settings page sections: worker status; models (`GET /models/status`, US-2.2 to US-2.4: each
  role's state, weights, and venv); corpus (new gateway `GET /corpus/status`, filtered to the
  global scope and the active profile's user scope); retention (the stored `retention_days`, an
  input, and Save).
- `GET /settings` also answers `retention_days`.
- Gateway `POST /settings/retention` with `{"retention_days": n}` (1-3650) writes the value
  through Hermes' own plugin-settings writer (`hermes_cli.plugins_settings.save_plugin_settings`,
  the one the Settings → Plugins form uses), then answers the stored settings. The worker's
  retention purge reads the profile's `config.yaml` on each run (US-4.5), so it uses the new
  period from its next run.
- Error codes `settings_unavailable` (no Hermes settings writer: outside the gateway) and
  `settings_managed` (an administrator-managed install or key).

## Capabilities

### New Capabilities
- `settings-page`: the ClaimCoach settings page with model status, corpus status, and the
  retention period the biller can change.

### Modified Capabilities
- None (`no-send-submit`'s pinned route tables gain the two gateway routes).

## Impact

- Two gateway routes; no worker change. The page stays feature-detected.
