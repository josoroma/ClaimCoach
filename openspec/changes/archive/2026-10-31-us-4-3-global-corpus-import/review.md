# Review: US-4.3

Change: us-4-3-global-corpus-import
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-4-scoped-retrieval
Verdict: pass after fixes; scope still needs Product Manager sign-off (NEEDS CLARIFICATION defaults)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Default embedding server may not serve `/v1/embeddings`, so a real `hermes claimcoach corpus import` would answer `model_unavailable` | Not fixed here (needs real models); evidence row stays UNVERIFIED; follow-up proposed |
| medium | One embedding call per item: unfilled batches, the model unpinned between items, long imports | The whole bundle is embedded in one `embed_documents` call (one hold, full batches of 16) |
| low | CLI dests `command` collided with Hermes' own top-level dest | `claimcoach_group` / `claimcoach_command`; `test_us_4_3_hermes_cli_registered` asserts Hermes' `command` is untouched |
| low | Bundle read: FIFO blocked forever; size checked by `stat` then unbounded read | `O_NONBLOCK` open, `S_ISREG` check, bounded read; `test_us_4_3_bundle_must_be_a_bounded_regular_file` |
| low | `POST /corpus/import` did not enforce the 5 MiB limit | `CorpusBundle` caps total text at 5 MiB, so the worker body is bounded too (same test) |
| low | "Future" and "stale" used the UTC date | Local date, one day of slack for the future check |
| low | All-or-nothing untested after partial success | `test_us_4_3_import_is_all_or_nothing_when_embedding_fails` (seeded scope unchanged); no-op lines removed |
| info | Import rollback wording; gateway imported `corpus.backup` at register time | Runbook rollback reworded; `backup` and Keychain code import lazily inside the local commands |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
