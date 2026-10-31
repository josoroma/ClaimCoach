# Spec Delta

## Purpose

Lets an appeal-levels rule card give the payer's appeal time limit, so the diagnosis can compute
the appeal deadline.

## ADDED Requirements

### Requirement: Appeal-levels cards may give an appeal time limit
An `appeal_levels` rule card MAY carry `appeal_limit_days`, a whole number of days from 1 to 3650;
it SHALL be stored with the card and read back unchanged. A limit on a card of any other topic, or
outside that range, SHALL fail the whole import.

#### Scenario: The appeal limit is stored with the card
- **WHEN** the manager imports an appeal_levels rule card with appeal_limit_days 180
- **THEN** the stored card reads back with appeal_limit_days 180

#### Scenario: A limit on another topic is refused
- **WHEN** a bundle holds a required_docs rule card with appeal_limit_days
- **THEN** the import fails with invalid_request and nothing is stored
