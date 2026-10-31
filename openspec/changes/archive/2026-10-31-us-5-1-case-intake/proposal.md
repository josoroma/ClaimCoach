# Proposal: US-5.1 Create a Case and Add Documents

## Why

PRD §6 story 1: a biller creates a case and drops in the EOB/ERA and the denial letter, or pastes
835 text, so ClaimCoach has what it needs to work the denial. PRD §5 limits intake to upload and
paste (no EHR or clearinghouse integration). US-3.3 already ships the pane's case API client; this
change gives it a backend and adds the paste box.

## What Changes

- `claimcoach/cases/models.py`: typed `CaseCreate`, `PastedText`, `SourceDocument`, `Case`,
  `DocumentAdded`, and the intake limits (formats, 16 MiB per file, 4 MiB of pasted text).
- `claimcoach/cases/errors.py`: `CaseError` and its subclasses, one fixed envelope code each.
- `claimcoach/cases/intake.py`: the in-memory single-file multipart parser and the content sniffer
  that decides `pdf`, `image`, `edi_835`, or `text` from the bytes, never from the filename.
- `claimcoach/cases/service.py`: `CaseService` (create, open, add a file, add pasted text) over the
  profile's encrypted user store.
- `CorpusStore`: a `case_items` table (sealed payload and data per row, audited
  `document_added`), deleted with the case's other content by `purge_case_content`.
- Worker `POST /cases`, `GET /cases/{case_id}`, `POST /cases/{case_id}/documents`,
  `POST /cases/{case_id}/paste`; gateway routes of the same paths, thin proxies (PC-4) that pass
  the active profile; `WorkerClient` methods for each.
- New error codes `document_too_large`, `unsupported_document`, `case_closed`.
- `plugin.js`: the pane is a drop zone (every dropped file goes into one case), gains a paste box,
  lists the case's source documents, keeps the open case across failures, refuses files over
  16 MiB before reading them, and adds to the open case instead of starting a new one; a "New
  case" button starts over.
- Makefile `case-new`, `case-add`, `case-paste`, `case-show`; `docs/runbooks/case-intake-extraction.md`.

## Capabilities

### New Capabilities
- `case-intake`: creating cases and attaching uploaded files or pasted text as source documents.

### Modified Capabilities
- `retention-purge`: the purge also deletes a case's attached source files and derived items.

## Impact

- US-5.2 reads the stored source files and writes its extraction as another case item.
- The gateway forwards the multipart body unparsed, so it needs no multipart library; the worker
  parses it in memory.
