# Proposal: US-8.2 Opt-In De-identified Aggregation and Weekly Summary

## Why

PRD §6 story 7: the manager reviews a weekly denial-pattern summary per payer and code. PRD §9:
the manager view aggregates de-identified outcome stats across profiles, which requires those
profiles to opt in, and never reads raw case documents. US-8.1 records outcomes; nothing groups
them yet, and an outcome row holds no payer or code to group by.

## What Changes

- `settings.py`: `share_outcome_stats` (off by default, a strict boolean) in the manifest's
  `config_schema`, so Settings → Plugins → ClaimCoach is where a profile opts in and out;
  `load_outcome_sharing(home)` reads one profile's choice and fails closed (anything but an
  explicit `true` is not shared).
- `outcomes/features.py`: `OutcomeFeatures`, the de-identified snapshot stored with an outcome:
  the payer as its global rule cards name it, the current diagnosis's denial reason, and its
  codes. `CaseService.record_outcome` takes it; a correction after the purge keeps the old one.
- `corpus/store.py`: the `outcomes` table gains a `features` column (added once to older
  tables); `read_outcomes(directory, since, until)` opens the database read-only, without the
  profile's key, under an SQLite authorizer that allows reading the `outcomes` table and nothing
  else.
- `outcomes/types.py` and `outcomes/summary.py`: `IsoWeek`, `OutcomeCounts` (with the total and
  the overturn rate), `CategoryRow`, `CodeRow`, `WeeklySummary`; `build_weekly_summary` over every
  profile under the Hermes root, skipping those that have not opted in.
- Worker `GET /outcomes/summary[?week=2026-W44]`, the gateway route, `WorkerClient.weekly_summary`.
- Desktop: the manager dashboard route shows the last completed week (sharing profiles, totals,
  and one line per payer and denial reason).
- `make outcomes-summary [WEEK=…]`; the `outcomes-and-export` runbook gains the summary.

## Capabilities

### New Capabilities
- `outcome-summary`: the opt-in, de-identified weekly summary of case outcomes for the manager.

### Modified Capabilities
- None (`case-outcome` keeps its requirements; the snapshot is stored alongside them).

## Impact

- One schema change: `outcomes.features TEXT`, added by `ALTER TABLE` the first time this
  version opens a user store; older rows keep `NULL` and count as unclassified.
- The outcomes table is readable without the profile's Keychain key, as it was before: it holds
  enums, dates, rule-card payer names, and pattern-checked codes only (US-8.3 adds procedure codes
  and payment statuses, never amounts).
