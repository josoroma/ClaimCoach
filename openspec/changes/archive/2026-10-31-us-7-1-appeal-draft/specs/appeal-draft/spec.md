# Spec Delta

## Purpose

Defines how a diagnosed case's appeal letter is drafted from the payer's rule cards and a letter
template, stored with the case, and labeled for human review.

## ADDED Requirements

### Requirement: Draft is generated from rule card and template
When the biller asks to draft an appeal for an open case with a current diagnosis, the worker
SHALL run a `draft` job that sends the letter facts, the diagnosis, the checklist documents, the
payer's rule cards, and the chosen letter template to the `drafting` role through the registered
`appeal_draft` prompt template, and SHALL store the reply's letter as the case's `AppealDraft`
naming the template and rule cards used. The job SHALL report `drafting` and then `done` as
`plugin.claimcoach.case.progress` events.

#### Scenario: Draft is generated from rule card and template
- **WHEN** the biller clicks Draft appeal on a diagnosed case with a payer rule card and a letter template
- **THEN** a draft letter is attached to the case

#### Scenario: The template is chosen by the denial reason
- **WHEN** no template is named and the corpus holds `appeal-prior-authorization` and `appeal`
- **THEN** a prior-authorization denial is drafted from `appeal-prior-authorization`

#### Scenario: An unusable reply stores nothing
- **WHEN** the drafting model answers without a letter
- **THEN** the job ends failed with drafting_failed and the case keeps its previous draft

### Requirement: Drafting needs a current diagnosis and a template
Drafting SHALL be refused with `not_diagnosed` when the case has no diagnosis or its fields
changed since the diagnosis, and with `no_letter_template` when no letter template matches;
refusals SHALL be answered before a job starts.

#### Scenario: A case that is not diagnosed
- **WHEN** the biller asks to draft an extracted case that has no diagnosis
- **THEN** the request is refused with not_diagnosed and no job starts

#### Scenario: No letter template on file
- **WHEN** the global corpus holds no letter template
- **THEN** the request is refused with no_letter_template

### Requirement: Draft carries the human-review label
Every stored draft SHALL carry the label "draft for human review", the pane SHALL head the draft
with it, and every export SHALL include it.

#### Scenario: Draft carries the human-review label
- **WHEN** a generated draft is displayed or exported
- **THEN** it is labeled "draft for human review"

### Requirement: The drafting server answers without hidden reasoning
The shipped `drafting` command SHALL start `mtplx serve` with `--reasoning off`, and the worker
SHALL add it once to an existing `models.yaml` whose `drafting` command is the unedited earlier
default, leaving an edited command unchanged.

#### Scenario: An unedited earlier models.yaml is migrated
- **WHEN** the worker starts with a models.yaml whose drafting command is the pre-US-7.1 default
- **THEN** the command ends with --reasoning off and the rest of the file is unchanged

### Requirement: A draft knows what it was drafted from
A draft SHALL record the extraction digest and diagnosis time it was drafted from, and the case
SHALL report the draft stale when either has changed since.

#### Scenario: A confirmed field makes the draft stale
- **WHEN** the biller confirms a field after the draft was made
- **THEN** the case reports the draft stale
