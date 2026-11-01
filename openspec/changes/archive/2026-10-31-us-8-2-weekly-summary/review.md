# Review: US-8.2

Change: us-8-2-weekly-summary
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the EPIC-8 changes
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | A snapshot over `OutcomeRow`'s 64 KiB limit (a claim of about 400 lines) was stored, then failed validation outside the reader's `try`: every later summary of that week, and every export, answered 500 | The service stores a snapshot over `MAX_FEATURES_CHARS` without its claim facts; the reader reads a longer one as unclassified (logged by type), and builds rows inside its `try`, so a row no version wrote makes only its profile `unreadable`. `test_us_8_2_a_huge_claim_keeps_a_summary_snapshot`, `test_us_8_2_an_oversized_stored_snapshot_is_unclassified`, `test_us_8_2_a_foreign_row_fails_only_its_profile` |
| medium | (shared, US-8.3) The unsealed `features` column held each case's billed and paid amounts per claim and line, readable without the key, against this change's own Impact statement and its reason for leaving dollars out | Amounts are no longer stored: each billed/paid pair is reduced to a payment status (`none`, `partial`, `full`), adjustments keep their codes only (US-8.3 design decision 1). Impact wording updated. `test_us_8_3_amounts_are_reduced_to_a_payment_status` checks no field of `ClaimFacts` is an amount |
| low | `9999-W52` and `0001-W01` passed `IsoWeek` and overflowed computing the bounds (502) | Weeks are limited to years 1970–9998 (`WEEK_YEARS`), refused with `invalid_request`; `test_us_8_2_invalid_weeks`, `test_us_8_2_bad_weeks_through_the_gateway` |
| low | The dashboard showed per payer and denial reason only; the story asks per payer and code | The dashboard lists `by_code` too; node `test_us_8_2_dashboard_shows_the_weekly_summary` |
| low | The opt-in scenario test did not check that profile B was never opened | `test_us_8_2_only_opted_in_profiles` records every SQLite connect and asserts none is B's scope |
| info | `\d` matched any script's digits (`٢٠٢٦-W43` returned 200) | ASCII `[0-9]` in the gateway check and `IsoWeek`; cases added to both week tests |
| info | With the Mac's zone, `timezone` was an abbreviation, ambiguous and wrong for one side of a DST week | The IANA name from `/etc/localtime` when it has one, else the abbreviation; `test_us_8_2_the_local_zone_is_named` |

Also checked by the reviewer and found sound: `share_outcome_stats` and its manifest mirror; `load_outcome_sharing` failing closed and validated on its own; the opt-in checked before any database opens; `_migrate_outcomes`; the `record_outcome` upsert (snapshot kept after a purge, close date kept, one transaction under the case lock); `read_outcomes` (read-only URI, closed on every path, column probe for older tables, UTC string ordering against local bounds); the authorizer (SELECT, attach, pragma, write, and functions denied); `outcome_features` (current diagnosis only, payer from the rule card); `OutcomeCounts`; grouping and once-per-code; DST week bounds; the routes and client; route pins; the dashboard's late-answer handling; the Makefile `WEEK` check; the runbook and upgrade rows; BR-1, BR-14.

## Re-verification

See the EPIC-8 `make verify` run recorded in the US-8.3 review (all three changes on one tree).
