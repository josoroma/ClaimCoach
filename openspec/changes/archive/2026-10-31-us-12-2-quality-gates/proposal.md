# Proposal: US-12.2 Classification and Draft-Quality Gates

## Why

PRD §4 sets denial-reason classification ≥ 85% on a labeled de-identified set (NFR-1) and ≥ 70%
of appeal letters accepted with only minor edits under the manager's rubric (NFR-2). SPECS.md left
the story NEEDS CLARIFICATION: where the labeled cases come from, and what "minor edits" means.
This change decides both with stated defaults (design decisions 1 and 2) and adds both evals.

## What Changes

- `tests/fixtures/denials/generate.py` and `denial_set.json`: 20 synthetic, de-identified denial
  cases (two per labeled family), each denied under a reason code `REASON_GUIDE` lists for its
  label, with documents rotating through 835 text, a denial letter, and an EOB PDF.
- `claimcoach.evals.datasets`: `DenialEvalSet`, `DraftReviewSet` and their loaders.
- `claimcoach.evals.flow`: `run_case` drives one case through the app (create, attach, extract,
  diagnose, draft, export) with `WorkerDriver`, and purges it afterwards.
- `claimcoach.evals.classification`: accuracy per labeled reason and overall; the gate fails
  under 85%. `claimcoach.evals.draft_acceptance`: the rubric (`similarity`), acceptance rate per
  denial reason; the gate fails under 70%.
- `python -m claimcoach.evals classification|drafts`; `make eval-classification`,
  `make eval-drafts`; the runbook's sections.
- The fake model server gains `responders` (a reply computed from the request).

## Capabilities

### New Capabilities
- `quality-gates`: the classification-accuracy and draft-acceptance evals and their gates.

### Modified Capabilities
- None.

## Impact

- Eval cases run in a profile's user scope and are purged when their flow ends (BR-7); the case
  rows and audit entries stay, as for any purge (US-4.5, US-4.6). The runbook recommends a
  dedicated profile.
- No new dependency (`difflib` is stdlib).
