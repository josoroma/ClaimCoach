# Design: US-14.2 Remove the Unread models_home Setting

## Context

`load_settings` validates the stored mapping all or nothing with `extra="forbid"`: one unknown key
resets every setting to its default and logs a warning (US-3.5). Hermes Desktop's settings form
may have saved `models_home` with the other values.

## Goals / Non-Goals

- Goals: the form shows only settings ClaimCoach reads; no profile loses its settings on upgrade.
- Non-Goals: a per-Mac setting for the weights folder (the worker keeps reading `MODELS_HOME`).

## Decisions

1. **Remove the setting rather than honour it.** The worker is shared by every profile, so a
   per-profile value has no single answer, and `make` always exports `MODELS_HOME`. Rejected:
   reading the default profile's value (silently ignores the other profiles' values).
2. **Drop the retired key before validation.** `RETIRED_SETTINGS` lists it; nothing else is
   loosened. Rejected: `extra="ignore"` (any typo'd or tampered key would stop failing closed).

## Risks / Trade-offs

- [An earlier version reads a config without `models_home`] → it uses the field's default; nothing fails.
