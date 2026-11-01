# Spec Delta

## Purpose

Defines the ClaimCoach statusbar item's typed state model and its local-only default.

## ADDED Requirements

### Requirement: The indicator shows local-only by default
The statusbar contribution on `STATUSBAR_AREAS.right` SHALL hold an `IndicatorState` that starts
as `local-only` and stays `local-only` unless `GET /settings` answers `richer_agent_access: true`.

#### Scenario: Indicator shows local-only by default
- **WHEN** the richer agent access setting is off and the statusbar renders
- **THEN** the ClaimCoach item shows the local-only state

#### Scenario: A failed settings read
- **WHEN** the settings read fails
- **THEN** the ClaimCoach item shows the local-only state
