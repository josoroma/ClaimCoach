# quality-gates Specification

## Purpose
Defines the classification-accuracy and draft-acceptance evals and their release gates.

## Requirements

### Requirement: Classification accuracy is measured on a labeled set
The classification eval SHALL run every case of a labeled de-identified denial set through the
app from upload to diagnosis, compare each diagnosed `DenialReason` with its label, and report
accuracy overall and per labeled reason. It SHALL exit non-zero when accuracy is below 85%. A case
that reaches no diagnosis SHALL count as misclassified and be listed with its error code.

#### Scenario: Classification eval reports accuracy
- **WHEN** the classification eval runs on the labeled de-identified eval set
- **THEN** it reports accuracy
- **AND** exits non-zero if accuracy is below 85%

#### Scenario: Accuracy at target passes
- **WHEN** every case is classified correctly
- **THEN** the eval exits 0 and the report says it passed

### Requirement: Eval cases do not stay in the profile
Each eval case SHALL be purged when its flow ends, whether it finished or not; cases that could
not be purged SHALL be counted in the command's output.

#### Scenario: Cases are purged
- **WHEN** the classification eval has run three cases
- **THEN** none of them holds a document or a diagnosis

### Requirement: Draft acceptance follows the manager rubric
The draft-acceptance eval SHALL count a draft as accepted with only minor edits when the letter
the manager approved keeps at least 85% of the draft's words in order and at least 85% of the
approved letter is the draft's words, and SHALL exit non-zero when fewer than 70% of the reviewed
drafts are. `make evals` SHALL count the eval as not measured, and the release as blocked, when no
review file is given.

#### Scenario: Seventy percent passes
- **WHEN** 7 of 10 reviewed drafts were approved with minor edits
- **THEN** the eval exits 0

#### Scenario: Below seventy percent blocks
- **WHEN** 6 of 10 were
- **THEN** the eval exits non-zero

#### Scenario: A cut draft is not a minor edit
- **WHEN** the manager approved the draft with its last quarter removed
- **THEN** that draft is not accepted with minor edits
