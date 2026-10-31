# corpus-import Specification

## Purpose
Defines how the manager imports reference material into the global corpus scope with provenance.

## Requirements

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

### Requirement: Rule cards may list required documents
A `required_docs` rule card MAY carry `required_documents`, a list of up to 30 entries of 1 to 200
characters (an empty list is no list); the list SHALL be stored with the card and read back
unchanged. A list on a card of any other topic SHALL fail the whole import.

#### Scenario: Required documents are stored with the card
- **WHEN** the manager imports a required_docs rule card with a list of required documents
- **THEN** the stored card reads back with the same list in the same order

#### Scenario: A list on another topic is refused
- **WHEN** a bundle holds a timely_filing rule card with required documents
- **THEN** the import fails with invalid_request and nothing is stored

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

### Requirement: Corpus commands reach the worker on the operator's port
The worker-backed corpus commands (`import`, `list`, `status`, `reindex`, `purge`, `audit`) SHALL
accept `--port` (default 18200) and send their requests to `127.0.0.1` on that port, and only
when the launcher recorded the running worker on that port; otherwise they SHALL answer
`worker_unavailable` without sending the token. A port outside 18200–18219 SHALL be refused
before any request is sent. The six worker-backed targets (`corpus-status`, `corpus-import`,
`corpus-list`, `corpus-reindex`, `corpus-purge`, `corpus-audit`) SHALL pass `WORKER_PORT` as that
port; the local targets (`corpus-backup`, `corpus-restore`, `corpus-key-export`,
`corpus-key-import`) SHALL pass none.

#### Scenario: A worker on another port
- **WHEN** the worker runs on port 18213 and the operator runs make corpus-list WORKER_PORT=18213
- **THEN** the corpus view is listed from that worker

#### Scenario: A port where the worker does not run
- **WHEN** the worker runs on 18200 and the operator runs a corpus command with --port 18205
- **THEN** the command answers worker_unavailable and nothing is sent to port 18205

#### Scenario: A port outside ClaimCoach's range
- **WHEN** the operator runs a corpus command with --port 80
- **THEN** the command stops with a usage error and exit 2, and nothing is sent
