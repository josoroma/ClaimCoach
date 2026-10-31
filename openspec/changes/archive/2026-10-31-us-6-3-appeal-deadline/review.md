# Review: US-6.3

Change: us-6-3-appeal-deadline
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The 835 denial date was not tied to the claim's transaction: every later `BPR` overwrote it, so a batch whose second transaction paid later gave the first claim that later date (a deadline months late) | Dates are read from the header of each transaction (`ST` resets them) and frozen at the first claim; a transaction without claims never dates one; `test_us_6_3_835_dates_come_from_the_first_claims_transaction` |
| medium | Without `DTM*405` the fallback was `BPR16` (the EFT date, days after the production date `GS04`), so the deadline could be days later than the payer's | `DTM*405`, else the group's `GS04`, else `BPR16`; design decision 1; `test_us_6_3_835_gives_the_denial_date` (GS04 ≠ BPR16) |
| medium | The deadline was built after the classification model returned, so a missing or failing 8B model hid it, and a corrected date needed two model runs | The deadline is computed by `CaseService` on every read of the case (`Case.deadline`), from the current extraction, cards, and date; design decision 5; `test_us_6_3_deadline_follows_the_case_without_a_model` (a failed classification still shows it) |
| medium | Any date was accepted as the denial date, so a misread year or a due date read as the notice date became a confident deadline | `implausible_denial_date` for a date after today or before a service date; `test_us_6_3_implausible_denial_date_is_not_used` |
| medium | The upgrade runbook said an earlier version opens the store, but it cannot read extractions holding `denial_date` | Data-migration row and rollback text: rolling back past US-6.3 needs the pre-upgrade backup; proposal Impact |
| low | Changing a card never refreshed the deadline; a stale deadline showed without a marker | Computed on read, so a re-imported card shows at once (same test as above); there is no stored deadline to go stale |
| low | Two `appeal_levels` cards of one payer (two spellings) raced by `doc_id` order | `payer_rule_cards` returns one card per topic, the most recently verified (US-6.2 fix); `test_us_6_3_two_spellings_use_the_freshest_limit` |
| low | A denial date near year 9999 made `compute_deadline` overflow and failed the whole diagnosis | Such a date is implausible (after today) and never reaches the computation; the deadline is no longer part of the diagnosis; `OverflowError` documented; the `9999-12-31` cases in `test_us_6_3_implausible_denial_date_is_not_used` and `test_us_6_3_denial_date_confirmable` |
| low | Dates were parsed leniently (`1760486400` as a Unix timestamp, datetimes accepted) | `IsoDate`: `YYYY-MM-DD` text only, for `denial_date` and `service_date`; `test_us_6_3_denial_date_confirmable` |
| low | `appeal_limit_days` accepted `true` (YAML `yes`, one day) and `"180"` | `StrictInt`; `test_us_6_3_limit_on_another_topic_refused` |
| low | An empty or malformed `DTM*405` blocked the next source | Only a valid date counts, else the next source is tried; `test_us_6_3_835_gives_the_denial_date` |
| low | An unreadable payer showed `no_rule_card`, pointing at the manager | `no_payer` status asks the biller to confirm the payer; `test_us_6_3_unknown_deadline_says_why`, `test_us_6_3_pane_unknown_deadline_says_why` |
| low | The import-refusal test held only the invalid card; no tests with two transactions or GS04 ≠ BPR16 | A valid card sits next to the invalid one; both 835 cases added |
| info | The validator did not check `due == denial_date + limit_days`; the error text read "belong on a appeal_levels card" | Checked now (`test_us_6_3_deadline_model_is_strict`); "is allowed only on appeal_levels cards" |
| info | Unreadable notice dates stop the pane's automatic diagnosis; older diagnoses had no deadline | Proposal Impact names the first; the second no longer applies (the deadline is on the case) |
| info | Evidence missing, tasks unchecked | Evidence recorded in `evidence/US-6.3/`; tasks checked before archive |

Also checked by the reviewer and found sound: BR-1, BR-11, BR-12, BR-14 (no date or deadline in a log or event); the typed contract and the 422 envelope for a bad date; the `appeal_limit_days` round trip; `compute_deadline`'s purity and calendar arithmetic across leap days; the pane's passed check and local date; `keep_confirmed` keeping the denial date; older extractions reading it as unreadable.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-6 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1075 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 87 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-6.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
an operator run of `make case-diagnose`, `case-show`, and `case-confirm` against a scratch worker
with fake models and synthetic data. The real-model tests skipped: the Qwen3-8B and Qwen3-14B
weights are not under `~/Models`, so the models' own answers are UNVERIFIED in the reports.
