# Spec Delta

## Purpose

Defines how the biller edits the stored appeal draft and exports it as a PDF or DOCX file to save.

## ADDED Requirements

### Requirement: Edits are saved to the draft
Saving the pane editor SHALL replace the stored draft's text with the biller's text and record
when it was edited, keeping the draft's label and provenance; it SHALL be refused with
`not_drafted` when the case has no draft and with `model_busy` while a draft job runs on the case.

#### Scenario: Edits are saved to the draft
- **WHEN** the biller edits the text of a draft open in the pane editor and saves
- **THEN** the stored draft contains the edited text

#### Scenario: An edit saved while drafting is kept
- **WHEN** the biller's edit is saved after a draft job started and before it stored its letter
- **THEN** the job ends failed with draft_edited and the stored draft holds the edit

#### Scenario: Editing a case without a draft
- **WHEN** the biller saves text for a case that has no draft
- **THEN** the request is refused with not_drafted

### Requirement: Export produces PDF and DOCX files of the saved draft
Exporting SHALL render the stored draft, never text from the request, as a valid PDF or DOCX file
that contains the draft text and the label "draft for human review", and SHALL answer with where
the file is, a suggested filename, and when it is removed.

#### Scenario: Export produces PDF
- **WHEN** the biller exports a saved draft as PDF
- **THEN** a valid PDF file containing the draft text is produced

#### Scenario: Export produces DOCX
- **WHEN** the biller exports a saved draft as DOCX
- **THEN** a valid DOCX file containing the draft text is produced

### Requirement: Exports are short-lived and owner-only
An export SHALL be written under the profile's ClaimCoach plugin data folder with owner-only
permissions, SHALL be audited, and SHALL be deleted 15 minutes after it was written or when the
worker stops, whichever comes first; the pane SHALL hand its path to the host's save dialog so the
biller chooses where the copy goes.

#### Scenario: An expired export is removed
- **WHEN** an export is older than 15 minutes when the sweep runs
- **THEN** the file is deleted

#### Scenario: Exports go when the worker stops
- **WHEN** the worker shuts down while an export is less than 15 minutes old
- **THEN** the file is deleted

#### Scenario: The biller chooses where the file is saved
- **WHEN** the biller exports from the pane on a host with captureGatewayFileDownload
- **THEN** the host's save dialog receives the export's path and suggested filename
