# Proposal: US-8.3 Manager-Approved Fine-Tune Export

## Why

PRD §9: the fine-tune export is an explicit, manager-approved export of de-identified case/outcome
pairs to a file, never automatic; PRD §6 story 5: the outcome feeds the future fine-tune set.
US-8.1 records outcomes and US-8.2 stores a de-identified snapshot with each; nothing exports them.

## What Changes

- `outcomes/features.py`: the snapshot gains `ClaimFacts` (what the classification model read,
  reduced to codes: adjustments, remark codes, and lines, each charge as a payment status of
  `none`, `partial`, or `full`; no dollar amount, claim number, date, or payer's printed name) and
  the appeal likelihood, taken when the outcome is recorded. A snapshot over 64 KiB is stored
  without its facts.
- `outcomes/types.py`: `ExportApproval {manager, approved}`, `FineTuneExportRequest`,
  `FineTuneRecord` (`format: "claimcoach-fine-tune-1"`, payer, facts, codes, denial reason, appeal
  likelihood, outcome), `FineTuneExport`, and `ExportNotApprovedError` (new code
  `export_not_approved`, 403).
- `outcomes/export.py`: `export_fine_tune` refuses before reading anything without an approval
  that says `true`; otherwise it reads the opted-in profiles' outcomes (US-8.2's reader), turns each
  labeled one into a record, withholds any record the US-3.1 regex validators match, writes JSON
  Lines to a new owner-only file in `<hermes root>/plugin-data/claimcoach/fine-tune/`, and appends
  the approval to `approvals.jsonl`.
- Worker and gateway `POST /outcomes/export`, `WorkerClient.export_fine_tune`; the dashboard's
  Fine-tune export section (manager name, approval checkbox, Export).
- `make outcomes-export MANAGER=… CONFIRM=yes`; the `outcomes-and-export` runbook.

## Capabilities

### New Capabilities
- `fine-tune-export`: the manager-approved, de-identified export of case/outcome pairs.

### Modified Capabilities
- None (`outcome-summary`'s snapshot gains optional fields; its requirements are unchanged).

## Impact

- Outcomes recorded before this change have no facts and are not exported (`unlabeled`).
- The export file is de-identified and kept until the manager deletes it.
