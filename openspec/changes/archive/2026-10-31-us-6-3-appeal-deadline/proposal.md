# Proposal: US-6.3 Appeal Deadline

## Why

PRD §6 story 3: the biller sees the appeal deadline on the case, so the appeal is filed before it
passes. PRD §9: payer rule cards hold timely-filing limits and appeal levels. A missed appeal
deadline loses the money for good, so the deadline must come from the payer's card and the
denial's own date, never from a guess.

## What Changes

- `CaseExtraction` gains `denial_date` (claim level, confirmable like every field): from an 835,
  the header of the transaction that holds the claim (`DTM*405`, else the group's `GS04`, else
  `BPR16`); on an EOB or a letter, the date of the payer's decision as the extraction model reads
  it. Dates (this one and service dates) are read only as `YYYY-MM-DD`.
- `RuleCard` gains `appeal_limit_days` (a strict whole number 1–3650, only on `appeal_levels`
  cards); `corpus list` shows it.
- `pipeline/deadline.py`: a pure, typed `compute_deadline(denial_date, limit_days)` (calendar days)
  and `appeal_deadline(extraction, cards, today)`, which says why there is no deadline when there
  is none (`no_payer`, `no_rule_card`, `no_appeal_limit`, `no_denial_date`,
  `implausible_denial_date`).
- `cases/diagnosis.py`: typed `AppealDeadline`. `Case.deadline` is computed by `CaseService`
  whenever a case is read, from the current extraction and the payer's current rule cards, so it
  never waits for a model and never goes stale.
- `plugin.js`: shows "Appeal by <date>" with the limit, the denial date, and the card it came from,
  flags a deadline that has passed, or says why the deadline is unknown and who fixes it; the
  denial date is a field the biller can confirm.
- Runbooks: the `appeal_levels` card format, the deadline checks, and the rollback limit.

## Capabilities

### New Capabilities
- `appeal-deadline`: the appeal deadline of a case.

### Modified Capabilities
- `case-extraction`: the extraction holds the denial date; dates are `YYYY-MM-DD` only.
- `corpus-import`: `appeal_levels` rule cards may give an appeal time limit in days.

## Impact

- An extraction stored before this change reads with `denial_date` unreadable, so it is listed
  for confirmation until the case is processed again or the biller confirms it.
- A case whose notice date could not be read has a field to confirm, so the pane does not start
  its diagnosis on its own (US-6.1: fields to confirm wait for the biller).
- An earlier version cannot read an extraction this version stored (its model forbids the new
  field): rolling back past this change needs the pre-upgrade backup (upgrade runbook).
- US-7.1 can print the deadline on the draft; US-10.x dashboards can sort by it.
