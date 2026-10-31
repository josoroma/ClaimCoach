# Tasks

## 1. Retention

- [x] 1.1 `RetentionPolicy`, `purge_expired`, `purge_case`, outcome storage; verify `test_us_4_5_expired_documents_purged`, `test_us_4_5_case_inside_retention_kept`, `test_us_4_5_outcomes_survive_deidentified`
- [x] 1.2 `load_settings(home)` and the per-profile policy; verify `test_us_4_5_retention_configurable`
- [x] 1.3 `RetentionJob` in the worker lifespan and `POST /corpus/purge`; verify `test_us_4_5_worker_runs_scheduled_purge`, `test_us_4_5_manual_purge_requires_confirm`

## 2. Operations

- [x] 2.1 Fill `docs/runbooks/phi-purge.md`, Makefile `corpus-purge`; verify `test_us_1_5_runbooks_have_sections`
- [x] 2.2 Record `evidence/US-4.5/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
