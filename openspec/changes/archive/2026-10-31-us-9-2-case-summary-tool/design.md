# Design: US-9.2 redacted case summary tool

## Context

A case's stored items (extraction, diagnosis, draft) hold case content: the printed payer name,
the claim number, dates, and amounts (BR-14). The handler guard (US-3.2) redacts every tool result
through the local PHI model, but its recall is below 100% by nature (NFR-4). US-8.2 already
reduces a case to a de-identified snapshot (rule-card payer, codes, enums).

## Goals / Non-Goals

Goals: a summary the agent can reason with (status, codes, payer, denial reason, likelihood, what
is next) that holds no PHI by construction, with the guard as a second layer.

Non-Goals: the explanation text, the checklist, the draft letter, or any date (they stay in the
pane); summaries of another profile's cases.

## Decisions

1. **De-identified by construction, then guarded.** Every field is an ID, an enum, a count, a
   pattern-checked code (`CaseCode`), or a global rule-card payer name. The printed payer name is
   replaced by the name of the rule cards that match it (US-6.2's matching), and is `null` when
   none does. Rejected: returning the printed payer name and relying on the guard (a misread can
   put a patient's name in the payer field; the guard's recall is not 100%).
2. **No dates (SPECS.md source: §7.2).** The deadline is its status only (`computed`,
   `no_rule_card`, …); the due date and denial date stay in the pane. Rejected: the due date
   (derived from the denial date, a date of an individual under HIPAA Safe Harbor).
3. **Status and stage.** `status` is `open` or `closed` (closed once an outcome is recorded);
   `stage` is the furthest step reached (`intake` → `extracted` → `diagnosed` → `drafted`).
   Codes are the current extraction's (`case_codes`, as the pane shows them), so a stale
   diagnosis never shows old codes; `diagnosis_stale` says when the reason may be out of date.
4. **The active profile, audited.** The handler sends `active_profile()`; the worker answers only
   that profile's case and appends `case_summarized` to its audit log (US-4.6), so an agent's read
   is as visible as the pane's `case_opened`. Rejected: no audit entry (agent access would be
   invisible to the audit).
5. **The only parameter is a case ID.** `CaseSummaryParams` has one field, `case_id`, with the
   `CaseId` pattern, and forbids extra keys; the schema says so and a test pins it.

## Risks / Trade-offs

- [A payer with no rule card shows as `null`] → the agent says so and suggests importing a card;
  the pane still shows the printed name.
- [Codes are read from extracted fields that could be misread] → each is pattern-checked
  (`CaseCode`), so no free text passes, and the guard runs over the result as well.
