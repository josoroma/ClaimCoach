# Test Report: US-7.2 Edit and Export the Draft

Change: us-7-2-edit-export-draft
Story: US-7.2
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; poppler `pdftotext`/`pdfinfo`, macOS `textutil` and Quick Look as independent readers

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Edits are saved to the draft: Then the stored draft contains the edited text" | PASS | `test_us_7_2_edits_saved`: after `POST /cases/{id}/draft/text` through the gateway, reopening the case shows `draft.text` equal to the edited text (with surrounding whitespace trimmed), `edited_at` set, the label and provenance unchanged, and a `draft_edited` audit entry. Also `test_us_7_2_edit_refusals` (`not_drafted`, `case_not_found`, `invalid_request` for blank text, more than 20,000 characters, extra fields, or non-JSON, and `case_closed`), `test_us_7_2_edit_refused_while_drafting` (`model_busy`), `test_us_7_2_edits_saved_while_drafting_are_kept`, and `test_us_7_2_a_worker_without_models_still_edits`. Pane (node): `test_us_7_2_pane_edits_saved` types into the editor; `Export PDF` is disabled with "Save the draft before exporting it."; `Save draft` posts `{text: edited}` to `/cases/{id}/draft/text`, and the stored draft shows the edited text with `edited: true`. Operator: `make case-edit` with a file that changed the salutation and added a line `EDITED-BY-BILLER-7.2 … café … “retro-auth” …` answered with `edited_at`. `make case-show` then gave a stored text equal to the file, the new salutation present, and the old one gone |
| 2 | "Export produces PDF: Then a valid PDF file containing the draft text is produced" | PASS | `test_us_7_2_export_pdf`: the exported file starts with `%PDF-`, holds every line of the letter, starts each page with the label, has `size_bytes` equal to the file size, and expires 15 minutes later. Also `test_us_7_2_pdf_keeps_unicode_and_paginates`, `test_us_7_2_pdf_keeps_text_after_control_characters`, `test_us_7_2_export_refusals`, `test_us_7_2_export_is_audited`, `test_us_7_2_export_files_are_owner_only`, and `test_us_7_2_export_through_the_gateway`. Pane (node): `test_us_7_2_pane_export_pdf` (`{format: 'pdf'}`, the save dialog is captured before the REST read and gets `appeal-draft-<case>.pdf`, then "The PDF went to the save dialog."). Operator: `make case-export FORMAT=pdf TO=<scratch>/out72` wrote a 34,980-byte file. `file` and `pdfinfo` read it as a PDF 1.7 of 1 page titled "Appeal letter (draft for human review)". `pdftotext` gave "Draft for human review", then the edited letter, including the `EDITED-BY-BILLER-7.2` line with its accented and typographic characters. The Quick Look render shows the same. A 15,038-character edited letter exported as 13 pages; each page's first line is "Draft for human review", and all 150 paragraphs are present |
| 3 | "Export produces DOCX: Then a valid DOCX file containing the draft text is produced" | PASS | `test_us_7_2_export_docx`: the package has `[Content_Types].xml` first, a main-document content type, relationships that resolve, the label in `core.xml`, and paragraphs that are the label followed by the stored text line for line (Unicode). `test_us_7_2_docx_reads_in_another_reader` (`textutil`), `test_us_7_2_docx_drops_characters_xml_cannot_hold`, `test_us_7_2_entity_text_is_kept_as_written`. Pane (node): `test_us_7_2_pane_export_docx` (`{format: 'docx'}`, saved as `appeal-draft-<case>.docx`). Operator: `make case-export FORMAT=docx TO=<scratch>/out72` wrote a 1,926-byte file. `file` reads it as "Microsoft Word 2007+", and `unzip -l` lists 4 parts. `textutil` gave "Draft for human review", then the edited letter. The Quick Look render shows the bold label and the edited text |

## Evidence Commands

```bash
make evidence STORY=US-7.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_7_2 -v
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/appeal_draft.test.mjs
# operator run on a fresh scratch worker (serve_draft_worker.py, as in US-7.1), WORKER_PORT=18215
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18215
make case-new; make case-paste CASE=case_b4dd6a3717c8de1c FILE=<scratch>/era.835
make case-edit CASE=case_b4dd6a3717c8de1c FILE=<scratch>/short.txt          # before any draft
make case-export CASE=case_b4dd6a3717c8de1c FORMAT=pdf                      # before any draft
make case-process ...; make case-diagnose ...; make case-draft CASE=case_b4dd6a3717c8de1c
make case-edit CASE=case_b4dd6a3717c8de1c FILE=<scratch>/edited.txt
make case-show CASE=case_b4dd6a3717c8de1c
make case-edit CASE=case_b4dd6a3717c8de1c FILE=<scratch>/blank.txt          # whitespace only
make case-edit CASE=case_b4dd6a3717c8de1c FILE=<scratch>/long.txt           # 20,001 characters
make case-export CASE=case_b4dd6a3717c8de1c FORMAT=pdf TO=<scratch>/out72
make case-export CASE=case_b4dd6a3717c8de1c FORMAT=docx TO=<scratch>/out72
make case-export CASE=case_b4dd6a3717c8de1c FORMAT=pdf TO=<scratch>/out72   # same target again
file <scratch>/out72/*; pdfinfo ...pdf; pdftotext -layout ...pdf -; textutil -convert txt -stdout ...docx; unzip -l ...docx
qlmanage -t -s 900 -o <scratch>/out72 <scratch>/out72/*.pdf <scratch>/out72/*.docx
make case-edit CASE=case_b4dd6a3717c8de1c FILE=<scratch>/longletter.txt     # 15,038 characters
make case-export CASE=case_b4dd6a3717c8de1c FORMAT=pdf TO=<scratch>/out72long
pdftotext -f N -l N ...pdf - | head -1                                       # every page
curl ... "http://127.0.0.1:18215/corpus/audit?profile=default&case_id=case_b4dd6a3717c8de1c"
```

```text
tests/test_us_7_2_edit_export.py ........................                [100%]
- generated xml file: .../evidence/US-7.2/junit.xml -
===================== 24 passed, 1167 deselected in 3.42s ======================
test_us_7_2_edits_saved PASSED
test_us_7_2_edit_refusals PASSED
test_us_7_2_edit_refused_while_drafting PASSED
test_us_7_2_export_pdf PASSED
test_us_7_2_pdf_keeps_unicode_and_paginates PASSED
test_us_7_2_export_docx PASSED
test_us_7_2_docx_reads_in_another_reader PASSED
test_us_7_2_export_refusals PASSED
test_us_7_2_edits_saved_while_drafting_are_kept PASSED
test_us_7_2_export_files_are_owner_only PASSED
test_us_7_2_expired_export_removed PASSED
test_us_7_2_worker_lifespan_sweeps_and_clears PASSED
test_us_7_2_export_through_the_gateway PASSED
(24 in all, 0 failed)

junit-node.xml: 4 US-7.2 cases, fail 0
  test_us_7_2_pane_edits_saved
  test_us_7_2_pane_export_pdf
  test_us_7_2_pane_export_docx
  test_us_7_2_pane_without_save_dialog_shows_where_the_file_is
appeal_draft.test.mjs (whole file): ℹ tests 17  ℹ pass 17  ℹ fail 0

$ make case-edit ... FILE=short.txt              (no draft yet)
    "error": {"code": "not_drafted", "message": "Draft the appeal before editing or exporting it."}
make: *** [case-edit] Error 22
$ make case-export ... FORMAT=pdf                (no draft yet)
{"ok":false,"error":{"code":"not_drafted","message":"Draft the appeal before editing or exporting it."}}
make: *** [case-export] Error 1
$ make case-edit ... FILE=edited.txt
edited_at: 2026-10-31T20:26:02.005505Z label: draft for human review template: appeal-prior-authorization
$ make case-show ...
stored == edited file: True | Dear Appeals Reviewer in text: True | old salutation gone: True | edited_at: 2026-10-31T20:26:02.005505Z | draft_stale: False
$ make case-edit ... FILE=blank.txt              -> 422 invalid_request
$ make case-edit ... FILE=long.txt (20,001 chars) -> 422 invalid_request

$ make case-export ... FORMAT=pdf TO=<scratch>/out72
    "format": "pdf", "path": "<scratch>/hermes/plugin-data/claimcoach/exports/appeal-draft-case_b4dd6a3717c8de1c-7774f69d98f2a3a2.pdf",
    "filename": "appeal-draft-case_b4dd6a3717c8de1c.pdf", "size_bytes": 34980, "expires_at": "2026-10-31T20:41:09.642512Z"
copied to <scratch>/out72/appeal-draft-case_b4dd6a3717c8de1c.pdf
$ make case-export ... FORMAT=docx TO=<scratch>/out72
    "format": "docx", "filename": "appeal-draft-case_b4dd6a3717c8de1c.docx", "size_bytes": 1926, "expires_at": "2026-10-31T20:41:09.861940Z"
copied to <scratch>/out72/appeal-draft-case_b4dd6a3717c8de1c.docx
$ make case-export ... FORMAT=pdf TO=<scratch>/out72        (same target again)
FileExistsError: [Errno 17] File exists: '<scratch>/out72/appeal-draft-case_b4dd6a3717c8de1c.pdf'
make: *** [case-export] Error 1
$ ls -l <scratch>/out72; stat exports
-rw-------  1926  appeal-draft-case_b4dd6a3717c8de1c.docx
-rw------- 34980  appeal-draft-case_b4dd6a3717c8de1c.pdf
drwx------ .../plugin-data/claimcoach/exports      (files inside: -rw-------)

$ file ...
appeal-draft-case_b4dd6a3717c8de1c.docx: Microsoft Word 2007+
appeal-draft-case_b4dd6a3717c8de1c.pdf:  PDF document, version 1.7, 1 pages
$ pdfinfo ...pdf
Title:           Appeal letter (draft for human review)
$ pdftotext -layout ...pdf -  (blank lines removed)
Draft for human review
  [Practice address]
  ACME Health Plan, Appeals Unit
  Re: Appeal of claim CLAIM-77, denied 2026-10-15
  Patient: [Patient name], member ID [Member ID]
  Dear Appeals Reviewer,
  We appeal the denial of procedure 99213 on 2026-09-01 (CO-197, N286). A retroactive
  ...
  EDITED-BY-BILLER-7.2: we also enclose the café-visit note — “retro-auth” request log.
  Enclosures:
  ...
  [Provider name and NPI]
$ textutil -convert txt -stdout ...docx  (blank lines removed)
Draft for human review
[Practice address]
...
Dear Appeals Reviewer,
...
EDITED-BY-BILLER-7.2: we also enclose the café-visit note — “retro-auth” request log.
...
$ unzip -l ...docx
[Content_Types].xml  _rels/.rels  word/document.xml  docProps/core.xml   (4 files)

$ (15,038-character edit) make case-export ... FORMAT=pdf TO=<scratch>/out72long
Pages:           13
page 1 first line: Draft for human review
...
page 13 first line: Draft for human review
"Synthetic paragraph" lines: 150   (the last, "Synthetic paragraph 149", present)

audit (case_b4dd6a3717c8de1c): draft_edited 2, draft_exported 4, case_drafted 1; entries are
  {seq, at, action, case_id, profile} only
worker log: 0 lines with "EDITED-BY-BILLER", "SYNTH-OPS-7", "Synthetic paragraph", or "Appeals Unit"
plaintext search of the scratch store (exports excluded): no match
after the worker stopped: exports folder empty (0 files); port 18215 free
```

Artifacts: `evidence/US-7.2/junit.xml`, `evidence/US-7.2/junit-node.xml`

## Failures

None.

## Notes

- The pane: the node tests render the pane under `register-fakes.mjs`, where the host save dialog
  (`captureGatewayFileDownload`, through the fake's `setFileDownload`) is faked. The editor and
  the real Electron save dialog were not seen in a live Hermes desktop. The operator run
  exercised the same worker routes with `make case-edit` and `make case-export`, so the stored
  text and the files on disk are real. Which folder the biller picks in the dialog is UNVERIFIED
  in a live app. The SPECS open question ("Where is the exported file written") is settled in
  design decision 4 (`openspec/changes/us-7-2-edit-export-draft/design.md`). The worker writes a
  short-lived file to the profile's `exports` folder, and the pane hands its path to the host's
  save dialog. `ctx.files.requestFolder()` is rejected because v0.22.5's SDK does not have it. A
  host without the dialog shows the path instead
  (`test_us_7_2_pane_without_save_dialog_shows_where_the_file_is`).
- Independent readers: the exporter renders PDFs with PyMuPDF, so I opened the files with
  poppler's `pdftotext` and `pdfinfo`, macOS `textutil` (Cocoa's Word importer), and Quick Look
  (`qlmanage -t`). I did not open them in Word, Pages, or Preview.
- Expiry: the export answers had `expires_at` 15 minutes after the export, and the folder emptied
  when the worker stopped (SIGTERM). I did not wait 15 minutes. The timed sweep is covered by
  `test_us_7_2_expired_export_removed` and `test_us_7_2_sweeper_runs_on_schedule`.
- The spec-delta scenarios (`openspec/changes/us-7-2-edit-export-draft/specs/`) were exercised as
  follows:
  - "An edit saved while drafting is kept": `test_us_7_2_edits_saved_while_drafting_are_kept`.
  - "Editing a case without a draft": `test_us_7_2_edit_refusals`, and the operator run returned
    `not_drafted`.
  - "An expired export is removed": `test_us_7_2_expired_export_removed`.
  - "Exports go when the worker stops": `test_us_7_2_worker_lifespan_sweeps_and_clears`, and in
    the operator run 0 files remained after the stop.
  - "The biller chooses where the file is saved": `test_us_7_2_pane_export_pdf` and
    `test_us_7_2_pane_export_docx`.
- How the operator run was isolated: a fresh scratch `HERMES_HOME`, run after the US-7.1 worker
  had stopped. Otherwise it used the same harness as US-7.1, on 127.0.0.1:18215, with only
  synthetic data. The real `~/.hermes` was not touched.
- Things I noticed, outside this story's criteria:
  - Refused `make` targets report different recipe exit codes. `case-edit` shows
    `make: *** Error 22` (curl's code), while `case-export` and `case-draft` show `Error 1`.
  - When `TO` names a file that already exists, the copy is refused as the runbook says, but the
    output is a raw Python `FileExistsError` traceback rather than a one-line message. The worker
    had already written a third export into the `exports` folder, which stays there until the
    15-minute sweep or the worker stops.
