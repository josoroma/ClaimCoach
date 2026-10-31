# appeal-deadline Specification

## Purpose
Defines the appeal deadline of a case: from the denial date and the payer rule card's appeal time
limit, or a stated reason why it is unknown.

## Requirements

### Requirement: Deadline is computed from the rule card
Whenever a case with an extraction is read, the case SHALL carry an `AppealDeadline` whose due date
equals its denial date plus the `appeal_limit_days` of the matched payer's `appeal_levels` rule
card, in calendar days, computed by the pure function `compute_deadline` from the current
extraction and cards; the pane SHALL show it with the limit, the denial date, and the card, and
SHALL say when it has passed.

#### Scenario: Deadline is computed from the rule card
- **WHEN** diagnosis runs on a case with a denial date and a payer rule card with an appeal time limit
- **THEN** the case shows the deadline equal to the denial date plus the rule card's limit

#### Scenario: A confirmed date or a new card shows at once
- **WHEN** the biller confirms the denial date, or the manager re-imports the payer's card with another limit
- **THEN** the next read of the case shows the new deadline without diagnosing again

#### Scenario: The deadline has passed
- **WHEN** the biller views a case whose deadline is before today
- **THEN** the pane says the deadline has passed

### Requirement: An unknown deadline says why
Without a readable payer, a matched rule card, an appeal limit, or a readable denial date, or with
a denial date after today or before a service date, the deadline SHALL have no due date and a
status of `no_payer`, `no_rule_card`, `no_appeal_limit`, `no_denial_date`, or
`implausible_denial_date` (in that order of precedence), and the pane SHALL name the reason; no
default limit SHALL be used.

#### Scenario: No rule card for the payer
- **WHEN** the case's payer matches no rule card
- **THEN** the deadline is unknown with status no_rule_card and no due date

#### Scenario: The denial date is unreadable
- **WHEN** the case's denial date could not be read and its payer card has a limit
- **THEN** the deadline is unknown with status no_denial_date until the biller confirms the date

#### Scenario: An implausible denial date
- **WHEN** the denial date read for the case is after today or before its date of service
- **THEN** the deadline is unknown with status implausible_denial_date and no due date
