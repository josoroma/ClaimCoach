# Tasks

## 1. Editing

- [x] 1.1 `DraftEdit`, `CaseService.edit_draft`, `draft_edited` audit, worker and gateway routes; verify `test_us_7_2_edits_saved`, `test_us_7_2_edit_refusals`

## 2. Export

- [x] 2.1 `letters/export.py` `render_pdf`, `render_docx`; verify `test_us_7_2_export_pdf`, `test_us_7_2_export_docx`
- [x] 2.2 `Exports` folder, owner-only files, 15-minute expiry and sweeper task; verify `test_us_7_2_expired_export_removed`, `test_us_7_2_export_files_are_owner_only`
- [x] 2.3 `ExportRequest`, `ExportedFile`, routes, `WorkerClient`; verify `test_us_7_2_export_through_the_gateway`

## 3. Pane and operations

- [x] 3.1 Pane editor, Save draft, Export PDF/DOCX through `captureGatewayFileDownload`; verify `node --test` `test_us_7_2_*`
- [x] 3.2 `make case-edit`, `make case-export`, runbook section; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.3 Record `evidence/US-7.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
