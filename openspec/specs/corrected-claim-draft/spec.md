# corrected-claim-draft Specification

## Purpose
Defines how ClaimCoach recommends a corrected claim or an appeal for a diagnosed case, and how it
drafts a corrected claim as a typed list of changes for human review, stored with the case,
exported as a file, and never sent.

## Requirements

### Requirement: A fixed table recommends the remedy
For a case whose diagnosis is current, the case view SHALL include a remedy recommendation
(`corrected_claim`, `appeal`, `either`, or `none`) computed on read by a pure function of the
denial reason, the case's CARC/RARC codes, and the payer's `corrected_claims` rule card, naming
its basis (`table`, `codes`, or `rule_card`) and the codes or card that decided it. No model SHALL
take part. A case without a current diagnosis SHALL have no recommendation.

#### Scenario: An appeal-only denial gets a recommendation, not a corrected-claim draft
- **WHEN** the biller opens a diagnosed case whose denial reason is medical_necessity
- **THEN** the pane recommends an appeal and shows why
- **AND** no corrected-claim draft is attached unless the biller asks for one

#### Scenario: Codes split eligibility and missing information
- **WHEN** an eligibility denial carries CARC 31, or a missing-information denial carries RARC M76
- **THEN** the recommendation is a corrected claim with basis codes, naming that code

#### Scenario: A payer's rule card overrides the table
- **WHEN** the payer's corrected_claims card maps bundling to corrected_claim
- **THEN** a bundling denial of that payer recommends a corrected claim with basis rule_card

### Requirement: The corrected-claim draft is a typed list of changes
When the biller asks for a corrected-claim draft of an open case with a current diagnosis, the
worker SHALL run a `correct` job that plans the changes from the case's codes by fixed rules, asks
the `drafting` role only for each change's action and why, and stores a `CorrectedClaimDraft`
labeled "draft for human review" with the original claim ID, a frequency code chosen by fixed
rules, and one to forty `ClaimCorrection`s. The job SHALL report `drafting` and then `done`.

#### Scenario: A correctable denial gets a list of changes for human review
- **WHEN** the biller requests a corrected-claim draft of a case whose recommended remedy is a corrected claim
- **THEN** a corrected-claim draft labeled "draft for human review" is attached to the case
- **AND** each change names a claim line or the claim, a field, an action, and the codes behind it

#### Scenario: Drafting needs a current diagnosis
- **WHEN** the biller asks for a corrected-claim draft of a case with no current diagnosis
- **THEN** the request is refused with not_diagnosed and no job starts

#### Scenario: An unprocessable claim is resubmitted as new
- **WHEN** the case carries RARC MA130
- **THEN** the draft's frequency code is 1

### Requirement: No value is invented
A change's current value SHALL be copied from the case's extraction, only for a line's procedure
code or service date that was read or confirmed, and SHALL otherwise be absent and shown as "not
in your documents". The parser SHALL refuse a model reply whose action or why names a CPT, HCPCS,
ICD-10, or modifier value the case's documents do not hold; the job SHALL then end
`correction_failed` and store nothing.

#### Scenario: A value missing from the documents is never invented
- **WHEN** the biller opens a corrected-claim draft that points at a field the extraction does not hold
- **THEN** that change's current value reads "not in your documents"
- **AND** no change proposes a new procedure, diagnosis, or modifier code

#### Scenario: A reply that proposes a code is refused
- **WHEN** the drafting model's action says to append modifier 59
- **THEN** the job ends failed with correction_failed and the case keeps its previous correction

### Requirement: A corrected-claim draft goes stale with its case
The case view SHALL set `correction_stale` when the extraction's digest or the diagnosis time
differs from those the correction was drafted from, and the pane SHALL offer to draft it again.

#### Scenario: A draft goes stale after re-extraction
- **WHEN** the case's fields change after a corrected-claim draft was made
- **THEN** the draft is marked stale and the pane offers to redraft it

### Requirement: The label is always present
`CorrectedClaimDraft.label` SHALL be the literal "draft for human review"; a stored draft without
it SHALL not validate, the pane SHALL not show a draft without it, and every export SHALL carry it.

#### Scenario: The label is always present
- **WHEN** a corrected-claim draft is shown or exported
- **THEN** it carries the label "draft for human review"

### Requirement: The corrected-claim draft exports as PDF or DOCX
`POST /cases/{case_id}/correction/export` SHALL render the stored correction, never request text,
as PDF or DOCX into the profile's exports folder as `corrected-claim-draft-<case id>.<ext>`,
deleted after 15 minutes, audited `correction_exported`; without a correction it SHALL answer
`not_corrected`.

#### Scenario: The corrected-claim draft exports as PDF or DOCX
- **WHEN** the biller exports a corrected-claim draft
- **THEN** a corrected-claim-draft-*.pdf or .docx file carrying the draft label is written

### Requirement: No submit control
Neither the correction routes nor the pane's corrected-claim controls SHALL send, submit, or
transmit anything; the US-7.3 route pins and loopback walk SHALL cover them.

#### Scenario: No submit control
- **WHEN** the routes and the pane's controls are walked
- **THEN** neither the corrected-claim route nor its pane control sends, submits, or transmits anything

### Requirement: Payers can state their corrected-claim rules
A `corrected_claims` rule card MAY carry `remedies` (denial reason → remedy) and
`frequency_code` (1, 7, or 8); those fields SHALL be refused on any other topic. A case's
diagnosis and appeal draft SHALL hold up to six rule cards.

#### Scenario: A corrected_claims card imports
- **WHEN** a bundle holds a corrected_claims card with remedies and a frequency code
- **THEN** it imports, and the same fields on a timely_filing card are refused
