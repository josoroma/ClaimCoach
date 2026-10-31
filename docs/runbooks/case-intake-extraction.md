# Runbook: case intake and extraction

Covers US-5.1 (create a case, attach PDF, PNG, JPEG, or text files and pasted 835 text) and US-5.2
(extract the claim's fields with Qwen3-VL-8B or the 835 reader, confirm what was unreadable).
Billers do this from the ClaimCoach pane; these commands are for operators checking the worker by
hand. Every
command talks to the worker on `127.0.0.1` only (BR-1, BR-2) and stores files encrypted in the
profile's user scope (BR-6, BR-13).

These commands print case content (filenames, extracted fields) to your terminal. Do not paste
their output into tickets, chats, or the agent transcript.

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- The profile's user scope opens: `make corpus-status` lists it with `"available": true` (the first
  `make case-new` creates it and its Keychain key).
- Prefer synthetic documents. Real patient documents belong in the pane, not in shell history.
- For extraction of PDFs and images: `Qwen3-VL-8B-Instruct-4bit` is under `MODELS_HOME` and the
  `mlx-vlm` venv exists (`make models-check` shows `extraction ... present  venv ok`; otherwise
  `make models-download ROLE=extraction CONFIRM=yes`). 835 text needs no model.

## Steps

1. Create a case (prints its `case_id`; `PROFILE` defaults to the active Hermes profile):

   ```bash
   make case-new
   ```

2. Attach an EOB, ERA, or denial letter (PDF, PNG, JPEG, or a UTF-8 text file, at most 16 MiB):

   ```bash
   make case-add CASE=case_0123456789abcdef FILE=/path/to/eob.pdf
   ```

3. Attach 835 text (or a letter's text) as pasted text (at most 4 MiB):

   ```bash
   make case-paste CASE=case_0123456789abcdef FILE=/path/to/era.835
   ```

4. List the case's source documents (this is a case access, so it is audited `case_opened`):

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

5. Extract the case's fields; progress events print until the job ends (`done` or `failed`):

   ```bash
   make case-process CASE=case_0123456789abcdef
   ```

6. Show the result, then confirm each field listed under `needs_confirmation`:

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

   ```bash
   make case-confirm CASE=case_0123456789abcdef FIELD=lines.0.service_date VALUE=2026-09-01
   ```

7. Run the offline tests, then the real-model extraction test (skips without the weights):

   ```bash
   make test-story STORY=US-5.1
   ```

   ```bash
   make test-story STORY=US-5.2
   ```

   ```bash
   make test-models
   ```

## Verification

- Step 1 prints `"ok": true` and a `case_id` of the form `case_` plus 16 hex digits.
- Steps 2 and 3 print the attached document: `kind` is `pdf` or `image` for files, `edi_835` for
  835 text (decided from the bytes, not the extension), `text` for anything else readable.
- Step 4 lists each document once, oldest first.
- A refusal prints the error envelope and stores nothing: `document_too_large` (413),
  `unsupported_document` (415; HEIC, TIFF, Word, or binary data), `case_closed` (409; the case's
  retention clock has started), `case_not_found` or `profile_not_found` (404).
- `make corpus-audit CASE=<id>` shows `case_created`, `document_added`, `case_opened`,
  `case_extracted`, and `field_confirmed` entries with IDs and times only.
- Step 5 prints `extracting` lines with rising percentages and ends with `done 100%`. A `failed`
  line names its code: `model_unavailable` (the extraction model is missing or not healthy),
  `model_busy` (memory guard queue), `case_closed`, `extraction_failed`, or `processing_timeout`
  (the job ran over 60 minutes); the command then exits 1. A document that could not be decoded
  is listed under `extraction.unread_sources`.
  A case with no document is refused before it starts with `no_documents`.
- Step 6 shows `extraction` with each field's `value` and `status` (`extracted`, `unreadable`,
  `confirmed`), including `denial_date` (US-6.3: from the 835 transaction holding the claim, its
  `DTM*405`, else `GS04`, else `BPR16`; or the notice date on an EOB or letter). Dates are
  confirmed as `YYYY-MM-DD` only. After `case-confirm`, the field is `confirmed` and leaves `needs_confirmation`; an
  invalid value is refused with `invalid_request` and changes nothing.

## Rollback

- A document attached by mistake stays until the case is purged. Close the case and purge it on
  request with the privacy officer's approval ([phi-purge](phi-purge.md)):
  `make corpus-purge PROFILE=<p> CASE=<id> CONFIRM=yes`.
- A case created by mistake holds nothing until a document is added; leave it, or purge it the
  same way.
- Cases are closed by recording an outcome (US-8.1); until then a case the pane left behind (New
  case, a reload) stays open and outside the retention clock. Find them with `make corpus-audit`
  (`case_created` without `case_closed`) and purge them on request as above.
- A wrong extraction is never final: confirm the correct value (step 6), or run step 5 again —
  confirmed values are kept across re-runs.
- If a real patient document was attached outside the pane, or case content appeared anywhere but
  the pane or this terminal, follow [phi-incident](phi-incident.md).
