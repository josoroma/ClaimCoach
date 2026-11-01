# Spec Delta

## Purpose

Defines how the biller records how a case ended and what recording it does to the case.

## ADDED Requirements

### Requirement: Outcome is recorded on the case
Marking a case's outcome SHALL store one of `overturned`, `upheld`, or `written_off` with the date
it was recorded in the de-identified outcomes table, and SHALL close the case in the same
transaction, auditing `outcome_recorded` and, when this closed the case, `case_closed`.

#### Scenario: Outcome is recorded on the case
- **WHEN** the biller marks an open case's outcome as overturned, upheld, or written off
- **THEN** the case stores that outcome and the case is closed

#### Scenario: A later outcome corrects the first
- **WHEN** the biller marks a closed case's outcome again
- **THEN** the stored outcome is replaced
- **AND** the case keeps the close date the first outcome gave it

### Requirement: Outcome requests are typed and checked
The outcome route SHALL accept only `{"outcome": <overturned|upheld|written_off>}` and SHALL be
refused with `invalid_request` for anything else, with `case_not_found` for an unknown case, and
with `model_busy` while a job runs on the case.

#### Scenario: An outcome while a job runs
- **WHEN** the biller marks the outcome of a case whose extraction, diagnosis, or draft is running
- **THEN** the request is refused with model_busy and nothing is stored

#### Scenario: An invalid outcome
- **WHEN** the outcome is not one of the three values or the body has another key
- **THEN** the request is refused with invalid_request and nothing is stored
