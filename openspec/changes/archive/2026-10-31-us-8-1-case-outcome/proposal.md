# Proposal: US-8.1 Record a Case Outcome

## Why

PRD §6 story 5: the biller marks a case's outcome later (overturned, upheld, written off), and
that outcome feeds the manager's dashboard (US-8.2) and the future fine-tune set (US-8.3). US-4.5
already created the de-identified `outcomes` table (an enum and a date) and kept it through the
retention purge; nothing records into it yet.

## What Changes

- `CorpusStore.record_outcome` stores the outcome and closes the case in one transaction: the
  first close starts the retention clock (US-4.5), a later outcome replaces the stored one and
  never restarts the clock. Audited `outcome_recorded`, plus `case_closed` when it closed the case.
- `cases/models.py`: typed `OutcomeRequest {outcome}`; `Case` carries `outcome` (the stored
  `OutcomeRecord`).
- `CaseService.record_outcome`, worker `POST /cases/{case_id}/outcome` (refused with
  `model_busy` while a job runs on the case), the gateway route, and `WorkerClient.record_outcome`.
- Pane: an Outcome section with **Mark overturned**, **Mark upheld**, and **Mark written off**; the
  recorded outcome and "Case closed" show once one is recorded.
- `make case-outcome CASE=… OUTCOME=overturned|upheld|written_off`; the new
  `outcomes-and-export` runbook.

## Capabilities

### New Capabilities
- `case-outcome`: recording how a case ended, which closes it.

### Modified Capabilities
- None (`no-send-submit`'s pinned route tables gain the outcome routes; the requirement is
  unchanged).

## Impact

- No schema change: the US-4.5 `outcomes` table already has the columns.
- Recording an outcome now closes the case, so the case takes no new documents, field
  confirmations, jobs, or edits afterwards, and its content is purged on the retention schedule.
