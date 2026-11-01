# Spec Delta

## Purpose

Defines the `/denial` slash command: what it answers with and without a case ID, and that its
reply holds no PHI.

## ADDED Requirements

### Requirement: /denial returns text without PHI
The plugin SHALL register `/denial`. Without a case ID it SHALL answer a fixed, PHI-free guide;
with a case ID it SHALL answer that case's summary rendered from the guarded
`claimcoach_case_summary` result, or a fixed error message. It SHALL never echo its argument and
never raise.

#### Scenario: /denial returns text without PHI
- **WHEN** the plugin is enabled and the biller runs /denial
- **THEN** the command returns text that contains no PHI

#### Scenario: /denial with a case ID summarizes the case
- **WHEN** the biller runs /denial with the ID of a case holding seeded PHI
- **THEN** the reply names the case's codes, payer, and status and none of the seeded PHI strings
