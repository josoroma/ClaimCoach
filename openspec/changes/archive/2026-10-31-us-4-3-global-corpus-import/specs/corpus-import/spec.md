# Spec Delta

## Purpose

Defines how the manager imports reference material into the global corpus scope with provenance.

## ADDED Requirements

### Requirement: Imported items keep provenance
`hermes claimcoach corpus import FILE` SHALL import rule cards, code entries, and letter templates
from a local YAML or JSON bundle into the global scope, keeping each item's `source` and
`verified_on`, and the corpus view SHALL show both.

#### Scenario: Imported rule cards keep provenance
- **WHEN** the manager imports a rule card with a source and a verified-on date with `hermes claimcoach corpus import`
- **THEN** the stored card shows its source and verified-on date in the corpus view

#### Scenario: Stale rule card flagged
- **WHEN** a card's verified-on date is more than 180 days old
- **THEN** the corpus view flags it as stale

### Requirement: Import is strict and all-or-nothing
An item without `source` or `verified_on`, with an unknown field, or with a duplicate key SHALL
fail the whole import, and nothing SHALL be stored.

#### Scenario: Missing provenance rejected
- **WHEN** a bundle contains a rule card without a `verified_on` date
- **THEN** the import fails with `invalid_request` and the global scope is unchanged

#### Scenario: Re-import replaces
- **WHEN** the same rule card is imported again with a newer verified-on date
- **THEN** the corpus holds one copy with the newer date

#### Scenario: Not a regular file
- **WHEN** the bundle path is a FIFO or larger than 5 MiB
- **THEN** the import is refused before anything is read past the limit
