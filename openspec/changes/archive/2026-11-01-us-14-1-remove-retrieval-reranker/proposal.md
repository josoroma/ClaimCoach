# Proposal: US-14.1 Remove Unused Retrieval and the Reranker

## Why

The EPIC-13 reference found that no production code calls the US-4.4 `Retriever`: US-6.1, US-6.2,
and US-7.1 chose exact lookups over similarity (similarity can pick a near-miss code or another
payer's card). So the `rerank` role, a ~16 GB download plus a local conversion that needs ~16 GB of
memory, never ran in a case flow, and the conversion machinery existed only for it. The product
owner decided on 2026-11-01 to remove retrieval and the reranker and to keep the vector index
(SPECS.md US-14.1).

## What Changes

- Model roles and registry: no `rerank` role, no `ConversionSpec`, no `acquire.convert`;
  `repo_id` is required. `ModelRegistry.load` drops a pre-US-14.1 file's `roles.rerank` and
  `acquire.convert` and leaves the file as it is; any other unknown key is still refused.
- Acquisition: downloads only. `Acquirer.convert`, `ConversionUnavailableError`,
  `ConversionRequest`, `ModelStatus.source_present`, the `converting` state, the manager's
  exclusive job mode and `any_resident`, `POST /models/convert` (gateway and worker),
  `WorkerClient.convert_model`, the `conversion_unavailable` error code, and `make models-convert`
  are removed.
- Corpus: `corpus/retrieve.py`, `Reranker`, `Embedder.embed_query`, `QUERY_INSTRUCTION`,
  `RetrievalQuery`, `RetrievedChunk`, and `CorpusService.retriever` are removed. Import and
  reindex still embed chunks; `CorpusStore.search` and `chunks` keep their case filter (BR-5).
- Tests: the fakes lose `/v1/rerank` and `convert`; US-4.4's tests exercise the store's search;
  conversion tests are removed; `tests/test_us_14_1_remove_retrieval.py` covers the scenarios.
- Docs: README-DEV.md, the model-download runbook, troubleshooting, evals, upgrade, and the
  runbook index.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `model-registry`: seven roles, and an older file still loads.
- `model-acquisition`: no local conversion.
- `memory-guard`: no conversion to hold loads back.
- `scoped-retrieval`: the guarantee moves to the index search; no reranker.

## Impact

- Removes about 130 statements from `plugin/`; coverage stays at 100%.
- A machine that downloaded the reranker keeps its folders under `MODELS_HOME`; nothing reads them,
  and the upgrade runbook says they may be removed by hand. An earlier version refuses a
  `models.yaml` without `rerank`, so a rollback needs the old copy.
- PRD §8 and §9 still describe retrieval and the reranker; SPECS.md records the decision.
