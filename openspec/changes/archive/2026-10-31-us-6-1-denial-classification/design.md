# Design: US-6.1 denial classification and appeal likelihood

## Context

US-5.2 stores a case's `CaseExtraction` (payer, amounts, lines, CARC/RARC/group codes) as a sealed
case item and runs extraction as a background job whose PHI-free progress events the gateway
relays (PC-4). The `classification` role in `models.yaml` is Qwen3-8B on `mlx_lm.server`. Prompts
come only from registered templates with per-call content in data blocks (US-3.6, BR-10). The
global corpus holds code entries keyed `CARC/<code>`, `RARC/<code>`, `GROUP/<code>` (US-4.3).
SPECS.md leaves one open question: the closed set of denial-reason labels.

## Goals / Non-Goals

Goals: classify a case's denial into a closed set, estimate appeal likelihood with at least one
reason, store it with the case, run it as a job with progress events, and show it in the pane.

Non-Goals: the plain-language explanation and checklist (US-6.2); the appeal deadline (US-6.3);
LoRA tuning on outcomes (PRD §8, later); measuring classification accuracy against the PRD §4
target (needs the labeled set, PRD §11 open item).

## Decisions

1. **The closed label set (resolves the open question).** `DenialReason` has eleven values, one
   per denial family that calls for a different action, each anchored on the CARCs that signal it:
   `eligibility` (27, 26, 31, 109, 177), `prior_authorization` (197, 15, 62, 198),
   `medical_necessity` (50, 56, 151, 167), `coding_error` (4, 5, 6, 11, 181, 182),
   `missing_information` (16, 252, 226, 227), `duplicate_claim` (18), `timely_filing` (29),
   `non_covered_service` (96, 204, 49, 119), `bundling` (97, 234, 236), `coordination_of_benefits`
   (22, 23), and `other`. The anchors are listed in the prompt as guidance, not applied as
   rules: a remark code or the payer's letter can move a case (CO-16 with N286 is missing
   information, CO-50 with an authorization remark is prior authorization). Rejected: the raw CARC
   as the label (about 300 codes, too fine to act on and to measure); free-text labels (cannot be
   validated, counted, or used by US-7.1 template selection).
2. **The model's JSON is validated; only its prose is shortened.** The reply must hold
   `denial_reason` from the set (compared lower-case, spaces and hyphens read as underscores),
   `appeal_likelihood` from `low|medium|high`, and a list of reason strings with at least one
   non-blank. Blank reasons are dropped, the first five are kept, and a reason over 300
   characters is clipped with `…`: temperature is 0, so refusing long prose would refuse the case
   on every retry. A missing or out-of-set label, or no reason, ends the job `failed` with
   `diagnosis_failed`; a previous diagnosis stays, and the message asks the biller to check the
   fields before diagnosing again (changed fields change the answer). Rejected: falling back to
   `other`/`low`, which shows a confident-looking answer the model never gave.
3. **Only the facts classification needs reach the prompt (data minimization).** The data blocks
   carry the payer, the claim totals, and per line the procedure code, amounts, adjustments
   (`CO-197 250.00`), and remark codes, as JSON; the claim number and service dates are left out.
   Unreadable values are `null`, so the model knows what is unknown. Rejected: sending the whole
   extraction, which adds identifiers without helping the label.
4. **Code notes are looked up exactly, not retrieved by similarity.** The case's codes are known
   keys, so `corpus/lookup.py` reads exactly the global `code` entries for them (BR-5 holds
   trivially: only global reference text and this case's own fields reach the prompt). Rejected:
   `Retriever` (US-4.4) here, which loads the 8B embedding and reranker models for an exact-match
   question and can return a near-miss code.
5. **A diagnosis is a separate case item that remembers what it read.** Kind `diagnosis`, item ID
   `diagnosis`, sealed like the extraction (BR-6), audited `case_diagnosed`, purged with the case
   (BR-7, the purge already deletes every case item). It records `extraction_digest`, the SHA-256
   of the extraction it read; `Case.diagnosis_stale` is true once a confirmation or a re-run
   changes the extraction, and the pane asks to diagnose again. Rejected: deleting the diagnosis
   on every change (loses the last answer while the biller confirms several fields); storing it
   inside the extraction item (couples two jobs' writes).
6. **The `case_items` `CHECK` follows `CaseItemKind`.** The schema's list is built from
   `CaseItemKind`, and a store whose table lacks a kind is rebuilt once at open, in one
   transaction (create, copy, drop, rename; `secure_delete` zeroes the old pages). Future kinds
   (drafts, EPIC-7) need no further migration code. Rejected: dropping the `CHECK` (loses a
   defence in depth); a second table per kind.
7. **Diagnosis is its own job kind; the pane chains it after a clean extraction.** `JobRegistry`
   keeps one job per case of either kind, so a diagnosis never reads an extraction that is being
   rewritten: a start request while a job runs returns that job with its `kind`, before the case
   is checked (so asking for a diagnosis during the first extraction joins it rather than
   answering `not_extracted`). The pane and `make case-*` follow the returned job and say when it
   is not the kind asked for. Progress is `classifying` at 0, then `done` at 1 (US-6.2 adds
   `explaining`). The pane starts a diagnosis when an extraction job ends `done` and every field
   was read; a case with fields to confirm waits for the biller, who confirms them and presses
   "Diagnose case" (diagnosing guesses would waste a model run and show advice built on them).
   The pane follows a job's events from before its start request is sent, so a job that ends
   before the answer arrives is never missed. Rejected: one job that extracts and then diagnoses (changes US-5.2's event
   sequence, and a confirmation would have to re-read every page to refresh the diagnosis);
   chaining in the gateway relay (the relay would start work, not only report it).
8. **One model provider serves the pipeline.** `create_app(pipeline_models=...)` (renamed from
   `vision`) is `ModelManager.use` in production and is asked for the role each step needs; tests
   route roles to separate fake servers.
9. **Errors.** `not_extracted` (409) when the case has no extraction yet, checked before a job
   starts; `diagnosis_failed` (502) when the reply does not validate; `model_unavailable`,
   `model_busy`, `case_closed`, and `processing_timeout` as for extraction. Job failures are
   logged by error type only (BR-14).

## Risks / Trade-offs

- [The 8B model may pick the wrong label] → reasons are shown with the label and the biller sees
  the codes it read. `test_us_6_1_classification_real_model` (marked `models`) is a smoke test on
  one synthetic case; accuracy is measured against the PRD §4 labeled set once it exists.
- [Model reasons may quote case content] → they are case content: sealed at rest, shown only in
  the pane, never logged or put in an event (BR-14).
- [The table rebuild runs on first open of an existing store] → one transaction; a failure rolls
  back and the store refuses to open (`CorpusError`), never half-migrated;
  `test_us_6_1_case_items_check_migrates` opens a store made with the old schema and
  `test_us_6_1_failed_migration_leaves_the_store_as_it_was` makes the copy fail.
- [A stale diagnosis may be acted on] → the pane says it is out of date until diagnosed again.
