# Review: US-8.1

Change: us-8-1-case-outcome
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | One click recorded the outcome and closed the case, which cannot be undone: a mis-click on a half-built case stranded it (no more documents, fields, jobs, or edits) | On an open case a Mark button only names the choice; a confirmation says what closing does, and the outcome is recorded on **Close the case** (or dropped on **Cancel**); a closed case is corrected in one click. Design decision 4; node `test_us_8_1_pane_outcome_recorded` |
| low | The busy check and the outcome's commit are not atomic: a job started in between ran on a closed case | Extraction and diagnosis now check that the case is open before they hold a model, as drafting already did (`CaseService.check_open`); `test_us_8_1_a_job_on_a_case_closed_meanwhile_holds_no_model` (both runners). Recorded in Risks / Trade-offs |
| low | The busy test used a stand-in for the job registry, so it could not catch a change in `JobRegistry.running` | `test_us_8_1_outcome_waits_for_a_real_job`: the worker's own `JobRegistry` with a runner held on an event: `model_busy` while it runs, recorded once it ends |
| low | After an outcome, the pane left upload, paste, Process, Confirm, Diagnose, Draft, and the draft editor enabled; a typed confirmation was lost to the `case_closed` refusal | A closed case disables them (Refresh, New case, the exports, and the outcome stay), drops and pastes are ignored, and the status line says the case is closed; node `a closed case keeps only Refresh, New case, the exports, and the outcome` |
| low | Task 2.1 named a test that does not exist (`test_us_8_1_outcome_through_the_gateway`) | Task text names the real tests (`test_us_8_1_outcome_through_the_worker`; the gateway path is `test_us_8_1_outcome_recorded`) |
| nit | `make case-outcome OUTCOME=up%` passed make's check (`filter` treats `%` as a wildcard) and reached the worker | `REQUIRE_OUTCOME` refuses a value holding `%` before `filter`; checked by hand: `OUTCOME=up%` and `OUTCOME=%` print the usage and exit 2 |

Also checked by the reviewer and found sound: the one-transaction outcome and close with `case_closed` audited only on the first close; corrections on closed and purged cases; the strict, enum-only `OutcomeRequest`; the gateway route (JSON only, size limit, case-ID check, envelope on every error, nothing echoed); `WorkerClient.record_outcome`; the case lock; `outcomeOf` against malformed bodies (`toString` included); BR-1, BR-2, BR-4 (route pins updated), BR-7, BR-14; the runbook sections and index.

## Re-verification

See the EPIC-8 `make verify` run recorded in the US-8.3 review (all three changes on one tree).
