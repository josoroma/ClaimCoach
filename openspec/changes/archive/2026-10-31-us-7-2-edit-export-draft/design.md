# Design: US-7.2 edit and export the draft

## Context

US-7.1 stores one `AppealDraft` per case as a sealed case item. The pane talks only to
`plugin_api.py` through `ctx.rest` (BR-2), which proxies to the worker. Hermes Desktop v0.22.5
has no `ctx.files` API in its SDK (the PRD's `ctx.files.requestFolder()` does not exist there);
it exports `captureGatewayFileDownload()`, which saves a file the gateway machine holds through
Electron's native save dialog (`desktop-plugin-sdk.md`, "Mental model"). The worker already reads
PDFs with PyMuPDF.

## Goals / Non-Goals

Goals: the biller edits the draft in the pane and saves it; exports a valid PDF or DOCX of the
saved draft, labeled for human review; chooses where the file goes.

Non-Goals: rich text (bold, lists) in the editor; letterhead or signature images; version history;
sending or uploading anything anywhere (US-7.3).

## Decisions

1. **The editor saves the whole text.** `POST /cases/{case_id}/draft/text` with `DraftEdit
   {text}` (1–20000 characters, not blank) replaces the draft's text and sets `edited_at`; the
   rest of the draft (label, template, provenance) is kept. It is refused with `not_drafted`
   when the case has no draft, `case_closed` for a closed case, and `model_busy` while a draft job
   runs on the case (its save would replace the edit a moment later). The read-modify-write holds
   the case lock. A draft job that finishes after an edit was saved (an edit from another window
   between the check and the job's start) keeps the edit: its save, under the same lock, refuses
   to replace a draft edited since the job started, and the job ends `draft_edited`. The pane
   disables Draft again while the editor holds unsaved text. Rejected: patches or diffs (one
   text of at most 20000 characters is small).
2. **Exports render the stored draft, never text from the request.** `ExportRequest` names only
   the format, so what is exported is what was saved; the pane disables Export while the editor
   has unsaved changes. A closed case can still export (reading changes nothing).
3. **PDF with PyMuPDF; DOCX with the standard library.** The PDF is laid out by `pymupdf.Story`
   (US Letter, one-inch margins, 11 pt sans-serif, one paragraph per line, Unicode text kept),
   built through the Story DOM, never from HTML text, so entity-looking text (`AT&amp;T`) stays as
   written; characters XML cannot hold (a NUL would end MuPDF's text) are dropped from both formats,
   then each page gets the header "Draft for human review" and the document title says so. The
   DOCX is the smallest valid WordprocessingML package (`[Content_Types].xml`, `_rels/.rels`,
   `word/document.xml`, `docProps/core.xml`): the label as a bold first paragraph, then one
   paragraph per line with spaces preserved; characters XML cannot hold are dropped. Rejected:
   `python-docx` or `reportlab` (new dependencies in the gateway and worker venvs for a few
   hundred lines of XML); HTML or plain-text export (not what the PRD asks).
4. **Where the file goes (SPECS.md open question): the biller chooses, through a short-lived
   gateway file.** The worker writes the export to `<profile home>/plugin-data/claimcoach/
   exports/` (mode 0700; the file 0600, written to a temporary name and renamed, named
   `appeal-draft-<case>-<random>.<ext>`) and answers `ExportedFile` with its absolute path, a
   suggested filename, its size, and when it expires. The pane captures
   `captureGatewayFileDownload()` before the export request and hands it the path: Hermes opens
   the native save dialog and the biller picks the folder. A host without it shows the path.
   Each export is deleted 15 minutes after it is written (swept before every export and every
   minute by a worker task), and every export is deleted when the worker stops, because it holds
   PHI in plaintext outside the encrypted user store (BR-6). Each export is audited
   `draft_exported` (IDs and times only). The pane allows one export at a time. Rejected: `ctx.files.requestFolder()` (not in v0.22.5's SDK); returning the bytes in
   the REST body (the pane has no API to save them); keeping exports (plaintext PHI at rest
   indefinitely); writing to a fixed folder such as `~/Downloads` (the biller would not choose).
5. **The export path is not PHI.** It holds the profile home, the opaque case ID, and a random
   suffix only; the filename the biller sees is `appeal-draft-<case>.<ext>`.

## Risks / Trade-offs

- [An export sits in plaintext for up to 15 minutes] → owner-only folder and file, random name,
  removed on schedule and at the next export; the runbook says how to remove one sooner.
- [A host without `captureGatewayFileDownload`] → the pane shows where the file is and for how
  long; `make case-export TO=…` copies it out.
- [Built-in fonts lack some scripts] → MuPDF's fallback fonts cover Latin, Greek, Cyrillic, and
  CJK; the test exports accented, typographic, and CJK text and reads it back.
