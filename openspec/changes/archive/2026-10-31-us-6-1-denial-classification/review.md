# Review: US-6.1

Change: us-6-1-denial-classification
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | In the chained path (extraction `done` → diagnosis) the pane stopped following events until the `/diagnose` answer arrived, so a diagnosis that failed at once (classification weights missing) left the pane at "Diagnosing … 0%" | The pane follows a job before its start request is sent (`follow` in `CasePane`; `afterExtraction` takes a `follow` callback that also refuses when a newer action replaced the chain); `a chained diagnosis that ends before its start is answered still ends the wait`, `New case before the chained diagnosis starts it nowhere` |
| medium | The spec and design said the pane diagnoses whenever an extraction ends `done`; the code (deliberately) chains only when no field needs confirmation | Spec requirement, scenarios ("The pane diagnoses after extraction" now requires every field read; new "Fields to confirm wait for the biller"), and design decision 7 now state the conditional chaining and why |
| low | `onDiagnose` did not mark the job as a diagnosis and `onProcess` did not clear the mark, so an early terminal event was taken for the wrong kind (a duplicate diagnosis, the wrong failure text) | `follow(caseId, diagnosing)` sets both on every start, Refresh, and New case; `Diagnose case follows its own job before the start is answered`, `Process after a Refresh during a diagnosis follows an extraction` |
| low | `POST /diagnose` checked for an extraction before looking for a running job, so asking during the first extraction answered `not_extracted`, contrary to the documented join | `JobRegistry.running`; both worker job routes return a running job before checking the case; `test_us_6_1_diagnose_during_first_extraction_joins_it` |
| low | `make case-process` / `case-diagnose` ignored `JobStarted.kind` and reported success for the other job | `CASE_JOB` reads `kind`, says on stderr when it follows another kind's job, and exits 1 then; runbook verification updated |
| low | Overlong reasons failed the job on every retry (temperature 0) while more than five were silently cut; the fixed messages promised a retry would help | Model prose is clipped, not refused (`replies.clip`: reasons 300, and in US-6.2 the explanation 2000, root cause 500, checklist reason 300); the `diagnosis_failed` message asks to check the fields before diagnosing again; design decision 2 updated; `test_us_6_1_replies_are_read_leniently_where_safe`, `test_us_6_2_long_text_is_clipped_not_refused` |
| low | "No job starts" was checked only through the gateway's relays; the migration's rollback path had no test | `test_us_6_1_diagnosis_requires_extraction` asserts the worker's registry holds no job; `test_us_6_1_failed_migration_leaves_the_store_as_it_was` makes the copy fail (a dangling row plus a leftover `case_items_next`) and checks the old table, its rows, and the leftover are intact; the migration now drops a leftover `case_items_next` before creating it |
| info | Tasks unchecked, evidence missing; the real-model test was described as an accuracy measurement | Evidence recorded in `evidence/US-6.1/`; tasks checked before archive; design risk now calls it a smoke test |
| info | CARC 24 (capitation) was anchored under coordination of benefits | Removed from the anchors (`REASON_GUIDE`, design decision 1) |

Also checked by the reviewer and found sound: BR-1, BR-5, BR-6, BR-7, BR-10, BR-11, BR-12, BR-14; the ES-8 envelopes of both `/diagnose` routes; the `case_items` migration (one transaction, CHECK detection, older versions open a migrated store); digest stability across a store round-trip; the `parse_reply` refactor (fuzzed: never raises); one job per case and cancellation on shutdown.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-6 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1075 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 87 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-6.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
an operator run of `make case-diagnose`, `case-show`, and `case-confirm` against a scratch worker
with fake models and synthetic data. The real-model tests skipped: the Qwen3-8B and Qwen3-14B
weights are not under `~/Models`, so the models' own answers are UNVERIFIED in the reports.
