# Spec Delta

## Purpose

Defines the ClaimCoach settings page: model status, corpus status, and the retention period.

## ADDED Requirements

### Requirement: The settings page registers when supported
`register(ctx)` SHALL register a ClaimCoach settings page through `ctx.registerSettingsPage` when
the host provides it, showing worker status, model status, corpus status, and retention.

#### Scenario: Settings page registers when supported
- **WHEN** register(ctx) runs on a host whose ctx provides registerSettingsPage
- **THEN** a ClaimCoach settings page is registered

#### Scenario: Settings degrade when unsupported
- **WHEN** register(ctx) runs on a host whose ctx lacks registerSettingsPage
- **THEN** registration completes without error

### Requirement: The retention period is saved through Hermes
`POST /settings/retention` SHALL accept only `{"retention_days": <1-3650>}`, SHALL save it with
Hermes' plugin-settings writer for the active profile, and SHALL answer the stored settings;
the worker's purge SHALL read the new period on its next run.

#### Scenario: Retention setting is saved
- **WHEN** the user changes the retention period on the settings page and saves
- **THEN** the worker reads the new retention period

#### Scenario: Retention cannot be saved
- **WHEN** the retention body is invalid, or Hermes' writer is missing or refuses a managed key
- **THEN** the request is refused with invalid_request, settings_unavailable, or settings_managed
  and nothing is written

### Requirement: Corpus status shows this profile only
`GET /corpus/status` in the gateway SHALL answer the global scope and the active profile's user
scope only.

#### Scenario: Another profile's scope is not shown
- **WHEN** two profiles have user scopes and the settings page reads corpus status
- **THEN** only the active profile's user scope is answered
