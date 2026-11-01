# Proposal: US-14.2 Remove the Unread models_home Setting

## Why

`models_home` appears in Hermes Desktop's settings form, but nothing reads it: the worker takes the
weights folder from `MODELS_HOME`. Settings belong to one profile, and the worker is shared by every
profile, so no profile's value could steer it (SPECS.md US-14.2).

## What Changes

- `ClaimCoachSettings` and `plugin.yaml`'s `config_schema` lose `models_home`.
- `load_settings` drops a stored `models_home` (`RETIRED_SETTINGS`) before validation, so a profile
  that saved it keeps its other settings; any other unknown key still resets them (US-3.5).
- README-DEV.md's Configuration section and the upgrade runbook say so.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `plugin-package`: the settings schema has no `models_home`, and a saved one is ignored.

## Impact

- Hermes Desktop no longer shows the setting. The weights folder is set with `MODELS_HOME`.
