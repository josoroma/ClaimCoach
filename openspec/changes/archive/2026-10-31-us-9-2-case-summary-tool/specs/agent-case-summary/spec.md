# Spec Delta

## Purpose

Defines the redacted case summary the Hermes agent reads by case ID: what it accepts, what it
holds, and that it holds no PHI.

## ADDED Requirements

### Requirement: Summary accepts only a case ID
The `claimcoach_case_summary` schema SHALL accept exactly one parameter, `case_id`, matching the
case ID pattern, and SHALL refuse any other key with the `invalid_request` envelope without
echoing the arguments.

#### Scenario: Summary accepts only a case ID
- **WHEN** the claimcoach_case_summary schema's parameters are inspected
- **THEN** the only accepted parameter is a case ID

### Requirement: Summary is redacted
`claimcoach_case_summary` SHALL answer the active profile's case with its codes, the payer as the
global rule cards name it, its status and stage, and its diagnosis enums, as a JSON string
validating against `CaseSummaryResult`; it SHALL hold no document text, claim number, date,
amount, or printed payer name, and SHALL pass through the handler guard. Every summary SHALL be
audited `case_summarized`.

#### Scenario: Summary is redacted
- **WHEN** a case with seeded PHI exists and the agent calls claimcoach_case_summary with that case ID
- **THEN** the returned JSON contains codes, payer name, and status and none of the seeded PHI strings

#### Scenario: Another profile's case is not found
- **WHEN** the agent calls claimcoach_case_summary with a case ID of another profile
- **THEN** the tool returns the case_not_found envelope
