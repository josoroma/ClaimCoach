# Design: US-8.1 record a case outcome

## Context

US-4.5 gave the user store a de-identified `outcomes` table (`case_id`, an outcome enum, a
date), `close_case` (which starts the 90-day retention clock), and `record_outcome`, used only by
tests. Every case route goes pane → `plugin_api.py` → worker (BR-2). A closed case refuses new
documents, confirmations, jobs, and edits (`case_closed`); exports of a closed case still work.

## Goals / Non-Goals

Goals: the biller marks a case overturned, upheld, or written off from the pane; the outcome is
stored de-identified and the case is closed.

Non-Goals: free-text outcome notes or amounts recovered (PHI risk, not asked for); reopening a
closed case; what the outcome feeds (US-8.2, US-8.3).

## Decisions

1. **Marking an outcome closes the case (SPECS.md open question).** One action: the outcome and
   the close are written in one transaction, so a case never has an outcome and stays open, and
   the retention clock starts when the biller says the case is over. Rejected: a separate Close
   action (two steps for the same moment, and an outcome on an open case would keep PHI past
   retention indefinitely if the second step were forgotten).
2. **A later outcome corrects the first; the clock does not restart.** Marking again replaces the
   stored outcome and its date (audited `outcome_recorded` each time) on a closed or purged case,
   because a mis-click must be fixable and the outcome is de-identified. The close keeps its first
   date (`COALESCE`), so correcting an outcome never extends retention. `case_closed` is audited
   only when this call closed the case. Rejected: refusing a second outcome (a mis-click would be
   permanent and wrong in the dashboard).
3. **Refused while a job runs on the case.** An extraction, diagnosis, or draft that is running
   would fail on save once the case is closed, so the route answers `model_busy` instead and the
   biller marks the outcome when the job ends. Rejected: cancelling the job (the biller may not
   expect the click to discard work).
4. **The pane asks before it closes a case.** Closing cannot be undone, so on an open case a
   Mark button only names the choice: a confirmation says the case will take no more documents,
   fields, or edits, and the outcome is recorded on **Close the case** (or dropped on
   **Cancel**). On a closed case a Mark button corrects the outcome at once. Once closed, the
   pane disables upload, paste, Process, Confirm, Diagnose, Draft, and the draft editor; Refresh,
   New case, the exports, and the outcome stay. Rejected: one click for both (review finding: a
   mis-click would strand a half-built case).
5. **The body is an enum only.** `OutcomeRequest {outcome}` with `extra="forbid"`; nothing
   free-text is stored or echoed (BR-7, BR-14).

## Risks / Trade-offs

- [A job started in the instant between the busy check and the outcome's commit] → it runs on a
  closed case; every job checks that its case is open before it holds a model
  (`test_us_7_1_a_closed_case_never_loads_the_model`) and its save is refused with `case_closed`,
  so no model work is wasted and nothing is stored.
- [A closed case cannot take more documents] → that is the intended end state; a new case is one
  click away, and the outcome can still be corrected.
