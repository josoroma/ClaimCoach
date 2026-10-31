# Proposal: US-4.5 Retention Auto-Purge of Source Documents

## Why

BR-7: source documents are purged automatically a configurable period after case close (default
90 days); outcomes are kept de-identified, so PHI is not kept longer than needed.

## What Changes

- `claimcoach/corpus/retention.py`: typed `RetentionPolicy` (from the profile's `retention_days`
  setting), `purge_expired()`, `purge_case()`, and `RetentionJob` (the worker's scheduled purge:
  at startup, then every 6 hours, over every profile's user scope).
- `CorpusStore`: `close_case()`, `record_outcome()` / `outcome()` in an `outcomes` table that holds
  only the `CaseOutcome` enum and a timestamp, and `purge_case_content()` (documents, chunks,
  vectors; then a WAL checkpoint so no deleted page lingers).
- `settings.load_settings(home)` reads a given profile's `config.yaml`, because the app-wide worker
  runs outside Hermes.
- Worker `POST /corpus/purge` (run now, or one case with `confirm: true`); CLI `corpus purge`;
  Makefile `corpus-purge`; `docs/runbooks/phi-purge.md` filled.

## Capabilities

### New Capabilities
- `retention-purge`: retention policy, scheduled and manual purge, de-identified outcomes.

### Modified Capabilities
- None.

## Impact

- US-8.1 (record an outcome) is not delivered yet; this change adds the de-identified outcome
  storage US-8.1 will write to, and US-8.1 adds the route and pane control.
