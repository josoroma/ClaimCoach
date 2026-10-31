# Proposal: US-7.1 Draft the Appeal Letter

## Why

PRD §6 story 4: the biller clicks **Draft appeal** and ClaimCoach drafts the letter from the
payer's rule card and a letter template. PRD §8 names Ternary-Bonsai-2-27B (the `drafting` role)
for drafting, and PRD §10 and BR-4 require every draft to be labeled "draft for human review".
EPIC-6 left each case with a diagnosis, an explanation, a checklist, and the payer's rule cards;
this story turns them into a first draft the biller edits (US-7.2).

## What Changes

- `claimcoach/letters/types.py`: typed `DraftRequest` (an optional `template_id`), `AppealDraft`
  (the letter text, the fixed `label`, the template and rule cards used, what it was drafted
  from, when), and `DRAFT_LABEL`. `letters/draft.py` re-exports them with the registered
  `appeal_draft` prompt template, the reply parser, template choice, and `Drafter`, the job runner.
- A third case job kind, `draft`, on the one-job-per-case registry: `drafting` (0) → `done` (1),
  relayed as `plugin.claimcoach.case.progress`; the `drafting` role is held through
  `ModelManager.use`, so the memory guard sequences it (BR-12).
- `CaseService`: `check_draftable` (open, extracted, diagnosed and not stale, a template on file),
  `save_draft`, the stored draft on `Case` with `draft_stale`. `CaseItemKind` gains `draft`
  (the US-6.1 CHECK migration rebuilds older stores once); `AuditAction` gains `case_drafted`.
- Worker `POST /cases/{case_id}/draft`, gateway `POST /cases/{case_id}/draft`, and
  `WorkerClient.start_draft`. New error codes `not_diagnosed`, `no_letter_template` (relayed,
  409) and `drafting_failed` (a job's last event).
- Pane: a **Draft appeal** button once the case is diagnosed, a "Drafting…" progress state, and
  the draft under the heading "Draft for human review".
- `make case-draft CASE=… [TEMPLATE=…]`; the `appeal-drafting` runbook.

## Capabilities

### New Capabilities
- `appeal-draft`: drafting a diagnosed case's appeal letter from the payer's rule cards and a
  letter template, labeled for human review.

### Modified Capabilities
- None. (Case jobs and case items gain a kind; their existing requirements are unchanged.)

## Impact

- Drafting loads the 27B model; the memory guard unloads any other ≥ 14B model first.
- Existing stores migrate their `case_items` CHECK once, as in US-6.1.
- US-7.2 edits and exports the stored draft; US-7.3 checks that nothing can send it.
