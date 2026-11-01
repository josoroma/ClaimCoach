# outcome-summary Specification

## Purpose
Defines the manager's weekly summary of case outcomes: which profiles it reads, what it reads,
and what it reports.

## Requirements

### Requirement: Only opted-in profiles are aggregated
The weekly summary SHALL include outcomes only from profiles whose `share_outcome_stats` setting
is an explicit `true`; a profile with the setting off, missing, invalid, or unreadable SHALL be
counted as not sharing and nothing of it SHALL be read.

#### Scenario: Only opted-in profiles are aggregated
- **WHEN** profiles A (opted in) and B (not opted in) have recorded outcomes and the weekly summary is built
- **THEN** it includes outcomes from A and none from B

#### Scenario: Revoking the opt-in
- **WHEN** a profile turns `share_outcome_stats` off and the summary is built again
- **THEN** the summary includes none of its outcomes

### Requirement: Aggregation never reads raw documents
The aggregation SHALL read only the de-identified outcomes table, opened read-only and without the
profile's key, under an SQLite authorizer that refuses every column of every other table.

#### Scenario: Aggregation never reads raw documents
- **WHEN** the aggregation job builds the weekly summary
- **THEN** it reads only the de-identified outcome tables and opens no source document

### Requirement: The summary reports counts per payer and denial reason and per payer and code
An outcome SHALL be stored with a de-identified snapshot (the payer as its rule cards name it, the
current diagnosis's denial reason, and its codes), and the summary of an ISO week in this Mac's
time zone SHALL report overturned, upheld, and written-off counts, their total, and the overturn
rate, for the week and per payer and denial reason and per payer and code.

#### Scenario: Counts and overturn rate
- **WHEN** a week holds outcomes of several payers and denial reasons
- **THEN** each payer and denial reason has its counts and overturn rate, and a case counts once per code

#### Scenario: An invalid week
- **WHEN** the summary is asked for a week that is not an ISO week that exists
- **THEN** the request is refused with invalid_request
