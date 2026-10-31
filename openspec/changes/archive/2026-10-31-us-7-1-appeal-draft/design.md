# Design: US-7.1 appeal letter draft

## Context

A diagnosed case (US-6.1, US-6.2) holds the denial reason, the appeal likelihood with reasons,
the explanation and root cause, the checklist from the payer's `required_docs` card, and the
payer's rule cards. The global corpus holds letter templates (US-4.3: `template_id`, title, body,
source, verified-on). Case jobs run one per case in the worker and report progress events
(US-5.2). Prompts come only from registered templates and per-call text is a data block (US-3.6,
BR-10). The `drafting` role is Ternary-Bonsai-2-27B served by `mtplx serve`.

## Goals / Non-Goals

Goals: a first appeal letter per diagnosed case, built from the payer's rule cards and a letter
template, stored with the case, labeled "draft for human review" wherever it is shown.

Non-Goals: editing and exporting (US-7.2); sending anything (US-7.3, BR-4: never); corrected-claim
drafts (US-7.4, needs clarification); patient identity in the letter (the extraction holds none).

## Decisions

1. **Drafting is a third job kind.** `draft` joins `extract` and `diagnose` on the one registry,
   so a draft never reads a diagnosis being rewritten. The job reports `drafting` (0) and `done`
   (1); a failure ends `failed` with its code, `drafting_failed` when the reply is unusable. The
   pane follows it like a diagnosis. Rejected: a synchronous route (a 27B letter takes minutes
   and would outlive the gateway's request timeout).
2. **Drafting needs a current diagnosis and a template.** `check_draftable` refuses before a job
   starts, and the job checks again: no extraction or diagnosis, or a diagnosis whose extraction
   digest no longer matches (the fields changed), is `not_diagnosed`; no template is
   `no_letter_template`; the job also checks again that the case is still open, so a case closed
   after Draft appeal never loads the 27B model. Rule cards are not required: a payer without cards still gets a draft,
   and the pane says the letter was drafted without the payer's rules. Rejected: drafting from a
   stale diagnosis (the letter would argue the wrong denial); refusing payers without cards (the
   biller could not start any letter for them).
3. **The template is chosen by name, not by the model.** `DraftRequest.template_id` picks one;
   without it the first stored of `appeal-<denial reason>` (underscores as hyphens, e.g.
   `appeal-prior-authorization`) and `appeal` is used. The draft names the template it used.
   Rejected: embedding search (could pick a corrected-claim template); letting the model choose.
4. **The prompt holds what a letter must cite, and nothing of another case.** Data blocks: the
   letter facts (payer, claim number, denial date, amounts, and per line the service date,
   procedure code, adjustments, and remark codes: diagnosis left the claim number and dates out,
   a letter cannot), the diagnosis (reason, likelihood reasons, explanation, root cause), the
   checklist documents as enclosures, the payer's rule cards (4000 characters each), and the
   template body (8000 characters). The extraction holds no patient or provider identity, so the
   instructions ask for bracketed placeholders (`[Patient name]`, `[Member ID]`, `[Provider name
   and NPI]`) the biller fills in. Everything stays in the worker and the loopback model (BR-1,
   BR-2, BR-5).
5. **The reply is one JSON object with the letter.** `{"letter": "…"}`; the text is stripped,
   clipped to 20000 characters (a retry at temperature 0 would write the same text), and must
   not be blank. The completion budget (8192 tokens) holds a letter of that length; a reply cut
   off at the budget fails `drafting_failed` and is named in the log. Rejected: free text (BR-10:
   a reply is parsed as JSON into a typed model).
6. **The label is part of the type.** `AppealDraft.label` is `Literal["draft for human review"]`
   with that default, so a stored draft without it does not validate; the pane heads the draft
   "Draft for human review", and US-7.2's PDF and DOCX carry it on every page and as the first
   line. The label is never left to the model's text.
7. **A draft knows what it was drafted from.** It records the extraction digest and the
   diagnosis time; `Case.draft_stale` is set when either changed since, and the pane asks to
   check or draft again. Drafting again replaces the draft (edits included); the pane's button
   says so once the draft has been edited. Rejected: keeping every version (a later story may
   add history; one stored draft keeps the purge and the pane simple).
8. **The draft is a sealed case item.** Kind `draft`, item ID `draft`, encrypted in the user
   scope (BR-6), purged with the case (BR-7), audited `case_drafted`; never logged or put in an
   event (BR-14).
9. **The drafting server runs without hidden reasoning.** `mtplx serve` defaults to
   `--reasoning auto`; the real Bonsai 27B then spent the whole budget reasoning and the reply
   stopped after 464 characters of letter (found by `test_us_7_1_draft_real_model`). The shipped
   command adds `--reasoning off`, and the worker migrates an existing `models.yaml` copy once
   when its `drafting` command is still the unedited old line. Rejected: a per-request
   `enable_thinking` (the server honors client thinking controls only for some clients);
   raising the budget alone (minutes of hidden reasoning per letter).

## Risks / Trade-offs

- [The model may invent facts or requirements] → the prompt holds only this case's fields and
  the payer's cards, placeholders stand in for what is unknown, and the draft is labeled for
  human review (BR-4).
- [A 27B model is slow and large] → the job runs in the background with progress events and the
  job deadline; the memory guard unloads other large models first.
- [The default template may not fit the denial] → the draft names the template used, and the
  operator can pick one with `make case-draft TEMPLATE=…`.
