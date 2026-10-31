# Proposal: US-5.2 Structured Extraction and Field Confirmation

## Why

PRD §6 story 2: claim lines, codes, dates, and amounts are extracted into a structured case and
the fields the model could not read are highlighted, so the biller only confirms what the model
missed. PRD §8 names Qwen3-VL-8B for EOB and letter pages; PC-4 says progress reaches the desktop
half as `plugin.claimcoach.*` events.

## What Changes

- `claimcoach/cases/extraction.py`: typed `FieldStatus`, `Extracted[T]`, `Adjustment`,
  `ClaimLine`, `CaseExtraction` (with field paths, the pending list, confirmation, and keeping
  confirmations across a re-run), `FieldConfirmation`, `JobStarted`, `JobEvents`.
- `claimcoach/pipeline/edi835.py`: a deterministic X12 835 reader for pasted or uploaded ERA text.
- `claimcoach/pipeline/extract.py`: `Extractor` — PyMuPDF rasterizes PDF pages (with their text
  layer), Qwen3-VL-8B reads each page or image through a registered prompt template (US-3.6), and
  every value is validated into `CaseExtraction`; what fails is `unreadable`.
- `claimcoach/pipeline/jobs.py`: `JobRegistry` — one background job per case, with an ordered,
  PHI-free list of `CaseProgressEvent`s that the gateway long-polls.
- `models/chat.py` sends images as OpenAI `image_url` parts and the served model's path;
  `ModelEndpoint` carries that path.
- Worker `POST /cases/{id}/extract`, `POST /cases/{id}/fields`, `GET /jobs/{job_id}/events`;
  gateway `POST /cases/{id}/process` (starts extraction and relays its events through
  `broadcast_plugin_event`) and `POST /cases/{id}/fields`; `GET /cases/{id}` returns the
  extraction and the fields that need confirmation.
- `plugin.js`: subscribes to `plugin.claimcoach.case.progress` with `ctx.onEvent`, shows progress,
  renders the extracted fields with unreadable ones highlighted, and confirms a field's value.
- Makefile `case-process`, `case-confirm`; the case runbook gains its extraction section.

## Capabilities

### New Capabilities
- `case-extraction`: structured extraction, unreadable-field highlighting, field confirmation,
  and progress events.

### Modified Capabilities
- None (`case-intake` from US-5.1 is unchanged; the `Case` body gains optional fields).

## Impact

- New dependency `pymupdf` (worker only; never imported by the gateway). See design risks.
- EPIC-6 classification reads `CaseExtraction`'s codes; US-12.3 times this job.
