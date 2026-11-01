# Design: US-14.1 Remove Unused Retrieval and the Reranker

## Context

Every install has a `models.yaml` copy in the data dir with a `rerank` role and an
`acquire.convert` command, written from the default on first start and possibly edited since.
`ModelRegistry` validates `roles` against the `ModelRole` enum with `extra="forbid"`.

## Goals / Non-Goals

- Goals: remove every path only the reranker used; keep existing installs starting.
- Non-Goals: removing the vector index or the embedding role (the product decision keeps them);
  editing PRD.md.

## Decisions

1. **An older `models.yaml` loads with the retired keys dropped, and is not rewritten.**
   `_without_retired` removes exactly `roles.rerank` and `acquire.convert` before validation.
   Rejected: refusing the file (every install would stop starting); rewriting it (a text edit of a
   YAML block the user may have changed; the existing command migrations replace single exact
   lines only).
2. **The index search keeps its case filter, and US-4.4's tests move to it.** `CorpusStore.search`
   and `chunks` filter by case in SQL before decrypting, which is the BR-5 guarantee US-4.4
   delivered. Rejected: deleting them with the retriever (the product decision keeps the index for
   a later story that needs similarity).
3. **The exclusive job mode goes with the conversion.** It existed so loads queue behind a ~16 GB
   conversion; downloads never needed it. Rejected: keeping it unused (dead code the coverage gate
   would have to keep testing).
4. **The runbook keeps its file name.** `model-download-convert.md` is linked from many places and
   listed by `test_us_1_5_runbooks_have_sections`; its title and content now cover downloads only.

## Risks / Trade-offs

- [Rollback to a version before US-14.1 with the new default file] → the upgrade runbook says to keep the old copy; an earlier version refuses a file without `rerank`.
- [A later story needs similarity search] → the index, the embedding role, and the case-filtered search are kept; a retriever can be added back with its own story.
