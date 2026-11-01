# Tasks

## 1. Models

- [x] 1.1 Remove the rerank role, the conversion recipe, `ConversionRequest`, `source_present`, `converting`, conversion in `Acquirer`, the exclusive job mode, `POST /models/convert` (gateway, worker, client), `conversion_unavailable`, and `make models-convert`; verify `test_us_14_1_no_rerank_role`, `test_us_14_1_no_conversion_route_or_target`, and the US-2.1, US-2.4, US-1.3, US-7.3, US-12.4 suites
- [x] 1.2 Drop a retired `rerank` role and `acquire.convert` when loading an older `models.yaml`, without rewriting it; verify `test_us_14_1_old_registry_still_loads`, `test_us_14_1_only_the_retired_keys_are_dropped`, `test_us_14_1_a_non_mapping_registry_is_still_refused`

## 2. Corpus

- [x] 2.1 Remove `corpus/retrieve.py`, `Reranker`, `embed_query`, `RetrievalQuery`, `RetrievedChunk`, and `CorpusService.retriever`; keep `CorpusStore.search` and `chunks`; verify `test_us_14_1_index_kept` and the rewritten US-4.4 suite

## 3. Docs

- [x] 3.1 Update README-DEV.md, `model-download-convert.md`, troubleshooting, evals, upgrade, and the runbook index; verify the US-13.2 and US-13.3 drift tests and `test_us_1_5_runbooks_have_sections`

## 4. Evidence

- [x] 4.1 Record `evidence/US-14.1/test-report.md` and `junit.xml`; verify `make evidence-check`
