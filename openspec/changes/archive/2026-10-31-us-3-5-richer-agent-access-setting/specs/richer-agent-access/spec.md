# Spec Delta

## Purpose

Defines the opt-in richer-agent-access setting and how the desktop half displays it, while its
scope is undecided.

## ADDED Requirements

### Requirement: Richer access is off by default
`ClaimCoachSettings` SHALL have `richer_agent_access`, default `false`, mirrored in the
`plugin.yaml` `config_schema`. Missing, unreadable, or invalid stored settings SHALL read as off.

#### Scenario: Richer access is off by default
- **WHEN** the settings of a fresh install are read
- **THEN** the richer agent access setting is off

#### Scenario: Invalid stored settings
- **WHEN** the stored ClaimCoach settings do not validate
- **THEN** the setting reads as off

### Requirement: Statusbar reflects richer access
The gateway SHALL serve `GET /settings` with the stored value, and the ClaimCoach statusbar item
SHALL show when richer agent access is on.

#### Scenario: Statusbar reflects richer access
- **WHEN** the richer agent access setting is on and the statusbar renders
- **THEN** the ClaimCoach item shows that richer agent access is enabled

### Requirement: The setting grants nothing until its scope is decided
No redaction or tool code SHALL read `richer_agent_access`; agent tool results SHALL stay
redacted whatever its value.

#### Scenario: Setting on, results still redacted
- **WHEN** richer agent access is on
- **THEN** only the settings model, the settings route, and the desktop display read it
