# Tasks

## 1. Extraction

- [x] 1.1 `cases/extraction.py` typed models, field paths, confirmation; verify `test_us_5_2_confirmed_fields_stored`, `test_us_5_2_values_validate_one_by_one`
- [x] 1.2 `pipeline/edi835.py`; verify `test_us_5_2_835_extraction_fills_case`
- [x] 1.3 `pipeline/extract.py` (PyMuPDF rasterize, Qwen3-VL per page, image parts in `chat_completion`); verify `test_us_5_2_extraction_fills_case_offline`, `test_us_5_2_unreadable_fields_highlighted`, `test_us_5_2_extraction_fills_case` (marked `models`)
- [x] 1.4 `pipeline/jobs.py` and worker routes; verify `test_us_5_2_progress_pushed_as_events`

## 2. Gateway and pane

- [x] 2.1 Gateway `/process` with the event relay, `/fields`; verify `test_us_5_2_progress_pushed_as_events`, `test_us_5_2_gateway_relays_worker_codes`, `test_us_5_2_relay_reports_a_lost_worker`, `test_us_5_2_one_relay_per_job`
- [x] 2.2 Pane progress via `ctx.onEvent`, highlighted fields, confirm; verify `node --test` `test_us_5_2_*`

## 3. Operations

- [x] 3.1 Makefile `case-process`, `case-confirm`; runbook extraction section; verify `test_us_1_5_runbooks_have_sections`
- [x] 3.2 Record `evidence/US-5.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
