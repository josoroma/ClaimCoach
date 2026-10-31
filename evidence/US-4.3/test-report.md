# Test Report: US-4.3 Global Corpus Import with Provenance

Change: us-4-3-global-corpus-import
Story: US-4.3
Verdict: pass
Coverage: 1/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (`~/.hermes/hermes-agent`, used only as the interpreter and CLI with a throwaway `HERMES_HOME`)

## Acceptance Criteria Evaluated

The scenario has two rows. Row 1 runs the import offline, through the ClaimCoach CLI handler and
the worker's corpus routes (in-process ASGI, fake embedding server). The real Hermes CLI registers
and parses the command. Row 2 is a live run of `hermes claimcoach corpus import` against a running
worker with a real embedding model, which did not happen (see Notes).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Imported rule cards keep provenance: Then the stored card shows its source and verified-on date in the corpus view" (CLI handler + worker routes in-process; real Hermes CLI registration and parsing) | PASS | `test_us_4_3_rule_card_keeps_provenance`: `corpus import rules.yaml` → exit 0, `imported 1 code, 1 letter_template, 1 rule_card (3 chunks)`. The `corpus list` row for `rule_card` shows `Aetna/timely_filing`, `Aetna provider manual 2026, section 7.2`, and the verified-on date (local today − 10 days), with no `STALE` flag. The stored view item has the same `source` and `verified_on`. `test_us_4_3_hermes_cli_registered`: parsed dests are `claimcoach_group` / `claimcoach_command`, and Hermes' own `command` dest is untouched. `test_us_4_3_real_hermes_registers_cli`: the real Hermes loader registers `claimcoach` only when the plugin is enabled. `test_us_4_3_hermes_claimcoach_corpus_import_help`: real `hermes_cli.main claimcoach corpus import --help` → exit 0, `usage: hermes claimcoach corpus import [-h] file`. Also: `test_us_4_3_import_is_all_or_nothing_when_embedding_fails` (embedder 503 → `ModelUnavailableError`, view unchanged); `test_us_4_3_bundle_must_be_a_bounded_regular_file` (a FIFO is refused at once, and a bundle over 5 MiB fails validation); `test_us_4_3_stale_card_flagged`, `test_us_4_3_missing_provenance_rejected` (+ `_by_worker`), `test_us_4_3_reimport_replaces`, `test_us_4_3_bundle_refusals`; `test_us_4_3_cli_worker_commands` (an unknown profile → `error: profile_not_found`, nothing created) |
| 2 | "Imported rule cards keep provenance: Then the stored card shows its source and verified-on date in the corpus view" (live `hermes claimcoach corpus import` against a running worker, real Qwen3-Embedding-8B) | UNVERIFIED | Not exercised: the task said not to start the real worker, and no real embedding model was run. See Notes |

## Evidence Commands

```bash
make evidence STORY=US-4.3
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
uv run pytest -m hermes -k us_4_3 -p no:cacheprovider --no-cov -v
# HERMES_HOME and MODELS_HOME pointed at a scratch directory:
make corpus-import FILE=<scratch>/missing.yaml
uv run python -m claimcoach.cli corpus --help
```

```text
tests/test_us_4_3_global_corpus_import.py .................              [100%]
- generated xml file: .../evidence/US-4.3/junit.xml -
====================== 17 passed, 829 deselected in 3.04s ======================

test_us_4_3_rule_card_keeps_provenance PASSED
test_us_4_3_stale_card_flagged PASSED
test_us_4_3_missing_provenance_rejected PASSED
test_us_4_3_missing_provenance_rejected_by_worker PASSED
test_us_4_3_import_is_all_or_nothing_when_embedding_fails PASSED
test_us_4_3_bundle_must_be_a_bounded_regular_file PASSED
test_us_4_3_hermes_cli_registered PASSED
test_us_4_3_cli_worker_commands PASSED

$ uv run pytest -m hermes -k us_4_3 -p no:cacheprovider --no-cov -v
tests/test_us_4_3_global_corpus_import.py::test_us_4_3_real_hermes_registers_cli PASSED
tests/test_us_4_3_global_corpus_import.py::test_us_4_3_hermes_claimcoach_corpus_import_help PASSED
====================== 2 passed, 844 deselected in 2.72s =======================

$ make corpus-import FILE=<scratch>/missing.yaml
usage: make corpus-import FILE=<bundle.yaml|.yml|.json>
make: *** [corpus-import] Error 2

$ uv run python -m claimcoach.cli corpus --help
  {import,list,status,reindex,purge,audit,backup,restore,key-export,key-import}
    import              import a YAML or JSON bundle into the global scope
    list                list the global corpus with source and verified-on
                        dates
```

Artifacts: `evidence/US-4.3/junit.xml`

## Failures

None.

## Notes

- SPECS.md keeps US-4.3 NEEDS CLARIFICATION. This run tested the defaults recorded in
  `openspec/changes/us-4-3-global-corpus-import/design.md`:
  - Format: one YAML/JSON bundle of `kind: rule_card | code | letter_template` items.
  - Each item requires `source` and `verified_on`, and unknown fields are rejected.
  - A bundle must be a regular file of at most 5 MiB.
  - A card is stale after 180 days by the local date, shown as `STALE`.
  - The manager is whoever runs the import on this Mac (no role check).
  The Product Manager may still change these.
- Row 2: `make evidence` includes both `@pytest.mark.hermes` tests, which run the real Hermes CLI
  (registration and argument parsing) with a throwaway `HERMES_HOME`. The full import through
  Hermes into a live worker was not run, because the task said not to start the worker. Real
  Qwen3-Embedding-8B vectors were not produced either (fake server).
- "Corpus view" here means `corpus list` / `GET /corpus/global`. The settings-page import and view
  are out of scope (design.md Non-Goals, US-10.3).
