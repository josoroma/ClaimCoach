# Proposal: US-7.2 Edit and Export the Draft

## Why

PRD §6 story 4: the biller edits the draft in the pane and exports it as PDF or DOCX, then sends
it through the practice's normal channels. PRD §10: nothing is auto-sent; the export is a file the
biller saves, never a transmission (US-7.3).

## What Changes

- `letters/types.py`: typed `DraftEdit` (the edited text), `ExportFormat` (`pdf`, `docx`),
  `ExportRequest`, and `ExportedFile` (where the file is, its suggested name, size, and expiry).
- `CaseService.edit_draft`: stores the biller's text as the draft (audited `draft_edited`),
  refused while a draft job runs on the case (`model_busy`) and without a draft (`not_drafted`).
- `letters/export.py`: `render_pdf` (PyMuPDF, US Letter, the label on every page) and
  `render_docx` (a minimal WordprocessingML package written with `zipfile`, the label as the first
  paragraph); `Exports` writes them under the profile's `plugin-data/claimcoach/exports/` folder
  (0700, files 0600) and deletes each 15 minutes after it was written.
- Worker `POST /cases/{case_id}/draft/text` and `POST /cases/{case_id}/export`, the gateway
  routes, and `WorkerClient.edit_draft` / `export_draft`. New error code `not_drafted`.
- Pane: an editor for the draft with **Save draft**, **Export PDF**, and **Export DOCX**; an
  export is saved through the SDK's `captureGatewayFileDownload()` (native save dialog; the
  biller picks the folder), feature-detected (PC-3).
- `make case-edit CASE=… FILE=…` and `make case-export CASE=… FORMAT=pdf|docx [TO=…]`; the
  `appeal-drafting` runbook covers both.

## Capabilities

### New Capabilities
- `draft-export`: editing the stored draft and exporting it as PDF or DOCX for the biller to save.

### Modified Capabilities
- None.

## Impact

- No new dependency: PDF rendering uses PyMuPDF, already the worker's PDF reader; DOCX uses the
  standard library.
- An export holds PHI in plaintext outside the encrypted store for at most 15 minutes, in a
  folder only the user can read; the biller's saved copy is theirs to keep.
