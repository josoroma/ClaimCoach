# Tasks

## 1. Backend

- [x] 1.1 `cases/models.py` (`CaseCreate`, `PastedText`, `SourceDocument`, `Case`, `DocumentAdded`, limits) and `cases/intake.py` (multipart parser, sniffer); verify `test_us_5_1_sniffs_kind_from_bytes`, `test_us_5_1_multipart_parser_rejects_malformed_bodies`
- [x] 1.2 `case_items` table in `CorpusStore`, purged with the case; verify `test_us_5_1_expired_attachments_purged`, `test_us_4_5_expired_documents_purged`
- [x] 1.3 `CaseService` and worker `/cases` routes; verify `test_us_5_1_pdf_or_image_attached`, `test_us_5_1_pasted_835_attached`, `test_us_5_1_refusals_store_nothing`
- [x] 1.4 Gateway `/cases` proxies and `WorkerClient` methods; verify `test_us_5_1_gateway_relays_intake_codes`, `test_us_5_1_gateway_reports_a_stopped_worker`

## 2. Pane

- [x] 2.1 Drop zone, paste box, document list, New case in `plugin.js` (JSDoc-typed); verify `node --test` `test_us_5_1_pane_*` and `tsc --checkJs`

## 3. Operations

- [x] 3.1 Makefile `case-new`, `case-add`, `case-paste`, `case-show`; `docs/runbooks/case-intake-extraction.md`; verify `test_us_1_5_runbooks_have_sections`, `make help`
- [x] 3.2 Record `evidence/US-5.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
