# Tasks

## 1. Retrieval

- [x] 1.1 `RetrievalQuery`, `RetrievedChunk`, case-filtered `search`/`chunks`; verify `test_us_4_4_query_requires_case`
- [x] 1.2 `Retriever` and `Reranker`; verify `test_us_4_4_other_case_chunks_never_retrieved`, `test_us_4_4_global_chunks_available`, `test_us_4_4_reranker_*`
- [x] 1.3 Record `evidence/US-4.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
