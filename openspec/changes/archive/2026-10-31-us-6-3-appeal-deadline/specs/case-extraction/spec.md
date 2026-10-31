# Spec Delta

## Purpose

Adds the denial date to the structured case, so the appeal deadline can count from it, and reads
dates only as `YYYY-MM-DD`.

## ADDED Requirements

### Requirement: The extraction holds the denial date
`CaseExtraction` SHALL hold `denial_date`, the date of the payer's decision: from an 835, the
header of the transaction holding the claim read (`DTM*405`, else the group's `GS04`, else
`BPR16`, each only when a valid date); from an EOB or letter, the date the extraction model reads.
Like every field it SHALL be stored as `unreadable` when missing or invalid, highlighted for
confirmation, and confirmable; an extraction stored without it SHALL read it as unreadable. The
denial date and the service dates SHALL be read and confirmed only as `YYYY-MM-DD` text.

#### Scenario: The 835 gives the denial date
- **WHEN** extraction runs on pasted 835 text with no DTM*405 segment
- **THEN** the case's denial date is the GS04 date of the claim's group, not a later BPR16 date

#### Scenario: A batch of 835 transactions
- **WHEN** the 835 holds a second transaction with other dates after the claim read
- **THEN** the denial date comes from the claim's own transaction

#### Scenario: An older extraction loads
- **WHEN** a case whose extraction was stored without a denial date is opened
- **THEN** the extraction loads with the denial date unreadable and listed for confirmation

#### Scenario: A number is not a date
- **WHEN** the biller confirms the denial date as 1760486400
- **THEN** the value is refused with invalid_request
