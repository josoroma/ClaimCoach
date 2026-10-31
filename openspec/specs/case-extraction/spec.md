# case-extraction Specification

## Purpose
Defines how a case's source documents become a typed, confirmable structured extraction, and how
extraction progress reaches the pane.

## Requirements

### Requirement: Extraction fills the structured case
Processing a case SHALL read every source document (835 text with the X12 reader, PDF pages and
images with the `extraction` role model through a registered prompt template) and store a
`CaseExtraction` with the payer, claim number, claim and line amounts, claim lines with procedure
code and service date, adjustments with group code, CARC, and amount, and RARC codes. Every value
SHALL validate against its typed field.

#### Scenario: Extraction fills the structured case
- **WHEN** extraction runs on a case with a synthetic EOB attached
- **THEN** the case holds claim lines with CARC, RARC, and group codes, dates, and amounts that validate against the typed CaseExtraction model

#### Scenario: 835 text is parsed without a model
- **WHEN** extraction runs on a case whose only source is pasted 835 text
- **THEN** the claim's lines, codes, dates, and amounts come from the 835 segments and no model is called

### Requirement: Unreadable fields are highlighted
A value the model did not give, or gave in a form that does not validate, SHALL be stored as
`unreadable` with no value and listed in the case's `needs_confirmation`, and the pane SHALL
highlight it for confirmation.

#### Scenario: Unreadable fields are highlighted
- **WHEN** extraction could not read a field and the biller opens the case
- **THEN** that field is highlighted for confirmation

### Requirement: Confirmed fields are stored as confirmed
`POST /cases/{case_id}/fields` SHALL validate the value with the field's type, store it as
`confirmed` (audited `field_confirmed`), and remove it from `needs_confirmation`; an invalid value
or unknown field SHALL be refused with `invalid_request` and change nothing. A re-run of
extraction SHALL keep confirmed claim-level values whose field still exists, and confirmed values
inside the lines, adjustments, or remark codes only when those come from the same source in the
same number of lines.

#### Scenario: Confirmed fields are stored as confirmed
- **WHEN** the biller enters and confirms the value of a highlighted field
- **THEN** the field is stored with the confirmed value and is no longer highlighted

#### Scenario: A re-run takes its lines from another source
- **WHEN** a confirmed line value exists and a re-run takes the lines from a newly attached 835
- **THEN** the line value comes from the 835 and the confirmed claim number is kept

### Requirement: Extraction progress is pushed as events
Each extraction stage SHALL produce a PHI-free `CaseProgressEvent` that the gateway broadcasts as
`plugin.claimcoach.case.progress`, ending with `done` or `failed`, and the pane SHALL receive it
through the gateway event stream.

#### Scenario: Extraction progress is pushed as events
- **WHEN** extraction is running and each stage completes
- **THEN** the worker's progress event is broadcast as plugin.claimcoach.case.progress and the pane receives it through the event stream

#### Scenario: The worker stops during extraction
- **WHEN** the gateway cannot reach the worker for three polls in a row
- **THEN** it broadcasts a failed progress event with worker_unavailable

#### Scenario: Extraction runs past its deadline
- **WHEN** a job runs longer than its deadline, or the relay outlives it without an end
- **THEN** a failed progress event with processing_timeout is broadcast

### Requirement: A model reply loses only what it got wrong
A `null` list, a malformed line, or a value of the wrong JSON type in the extraction model's reply
SHALL make only that value or item unreadable; every other value of the page SHALL be kept.

#### Scenario: A reply with null lists and a malformed line
- **WHEN** the model answers with null adjustment and remark lists, a malformed line next to a good one, and true as an amount
- **THEN** the good line is stored and only the bad values are listed for confirmation
