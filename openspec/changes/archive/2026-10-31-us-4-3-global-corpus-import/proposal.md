# Proposal: US-4.3 Global Corpus Import with Provenance

## Why

Billers must work from current, traceable reference material (PRD §6 story 7, §11: rule cards
carry a source and a verified-on date; stale cards are flagged). The manager needs one command to
load the code knowledge base, payer rule cards, and letter templates into the global scope.

## What Changes

- `claimcoach/corpus/types.py`: typed `RuleCard`, `CodeEntry`, `LetterTemplate` (each with required
  `source` and `verified_on`), `CorpusBundle`, `ImportResult`, `CorpusViewItem`,
  `CorpusViewResponse`; `parse_bundle()` reads a local YAML or JSON file.
- `claimcoach/corpus/importer.py`: `import_bundle()` (all-or-nothing, idempotent upsert keyed by
  item) and `corpus_view()` (provenance plus a `stale` flag).
- Worker `POST /corpus/import`, `GET /corpus/global`; `WorkerClient` methods for them.
- `claimcoach/cli.py`: `hermes claimcoach corpus import|list|status|reindex|purge|audit|backup|
  restore`, registered through `ctx.register_cli_command`, also runnable as
  `python -m claimcoach.cli` (Makefile `corpus-import`, `corpus-list`).
- Runbook import section.

## Capabilities

### New Capabilities
- `corpus-import`: bundle format, provenance, stale flag, the import command.

### Modified Capabilities
- None.

## Impact

- `register(ctx)` also registers the `claimcoach` CLI command. SPECS.md keeps US-4.3 NEEDS
  CLARIFICATION; the defaults below are for the Product Manager to confirm.
