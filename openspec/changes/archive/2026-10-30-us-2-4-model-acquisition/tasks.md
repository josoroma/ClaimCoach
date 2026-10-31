# Tasks

## 1. Acquisition

- [x] 1.1 Presence fields in `ModelStatus`; verify `test_us_2_4_missing_models_reported`
- [x] 1.2 Implement `claimcoach/models/acquire.py` (`DownloadRequest`, `ConversionRequest`, `AcquireResult`, `Acquirer`); verify `test_us_2_4_download_requires_confirmation`, `test_us_2_4_declined_download_no_network`, `test_us_2_4_reranker_converted_locally`

## 2. Routes

- [x] 2.1 Worker and gateway `POST /models/download`, `POST /models/convert`; `WorkerClient` POST and envelope relay; verify the proxy tests

## 3. Operations

- [x] 3.1 Makefile `models-download`, `models-convert`; write `docs/runbooks/model-download-convert.md`; verify the runbook test
- [x] 3.2 Record `evidence/US-2.4/test-report.md` and `junit.xml`
