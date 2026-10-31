# Test Report: US-7.1 Draft the Appeal Letter

Change: us-7-1-appeal-draft
Story: US-7.1
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; `~/Models/Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` and the `mtplx` venv present

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Draft is generated from rule card and template: Then a draft letter is attached to the case" | PASS | `test_us_7_1_draft_from_rule_card_and_template`: a diagnosed case (ACME Health cards and the three synthetic templates imported) is drafted through the gateway's `POST /cases/{id}/draft`. The opened case has `draft.text` equal to the drafting model's letter, `template_id` `appeal-prior-authorization`, `rule_cards` `ACME Health/appeal_levels` and `ACME Health/required_docs`, `draft_stale` false, and the events `drafting 0.0`, `done 1.0`. The template body and the required-docs card reached the drafting model as data, and the audit ends `case_drafted`, `case_opened`. Also `test_us_7_1_template_chosen_by_denial_reason[...]` (3 cases), `test_us_7_1_no_letter_template`, `test_us_7_1_drafting_needs_a_current_diagnosis`, `test_us_7_1_unusable_reply_stores_nothing[...]` (5 cases), `test_us_7_1_prompt_carries_letter_facts`, `test_us_7_1_draft_stale_after_confirmed_field`, `test_us_7_1_progress_relayed` (no letter text in any event). Pane (node): `test_us_7_1_pane_draft_from_rule_card_and_template` clicks the `Draft appeal` button, sees `Drafting the appeal for case … 0%`, and after `done` shows the draft with "Drafted from the template appeal-prior-authorization with the rule cards ACME Health/appeal_levels, ACME Health/required_docs." Real model: `test_us_7_1_draft_real_model` PASSED (43 s). Bonsai 27B, started by `ModelManager` from `~/Models`, drafted the synthetic case. The letter contains `CLAIM-77` and the label. Operator: `make case-draft` printed `drafting 0%`, `done 100%`, and `make case-show` showed the draft with `template_id` `appeal-prior-authorization`, both ACME Health cards, and `draft_stale` false |
| 2 | "Draft carries the human-review label: Then it is labeled \"draft for human review\"" | PASS | `test_us_7_1_draft_carries_review_label`: `case.draft.label == "draft for human review"`, the gateway's JSON has the same label, every page of the rendered PDF starts with "Draft for human review" and the PDF title contains it, and in the DOCX the label comes before the letter. Pane (node): `test_us_7_1_pane_draft_carries_review_label` checks the `h3` "Draft for human review" and the editor's `aria-label` "Appeal letter (draft for human review)". A draft whose label is missing, `final`, or wrongly cased is not shown. Operator: `make case-show` showed `"label": "draft for human review"`. Both exports were checked with readers other than the exporter's PyMuPDF: `pdfinfo` gave the title `Appeal letter (draft for human review)`, `pdftotext` gave "Draft for human review" as the first line, and `textutil` gave the same first line for the DOCX. Quick Look renders of both files show the label above the letter. The real-model letter also carried the label (row 1) |

## Evidence Commands

```bash
make evidence STORY=US-7.1
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_7_1 -v
uv run pytest -m models -k us_7 -rA --no-cov -p no:cacheprovider
lsof -nP -iTCP:18206 -sTCP:LISTEN          # after the real-model run
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/appeal_draft.test.mjs
# operator run against a scratch worker (serve_draft_worker.py: real create_app, InMemoryKeyProvider,
# fake embedding, classification, explanation, and drafting servers; synthetic ERA_835, the ACME
# Health rule cards and code notes of tests/fakes/diagnosis.py, and two synthetic letter templates)
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18214
make case-new; make case-paste CASE=case_d85c2f9b3487b1ea FILE=<scratch>/era.835
make case-draft CASE=case_d85c2f9b3487b1ea                  # before extraction and diagnosis
make case-process CASE=case_d85c2f9b3487b1ea; make case-draft CASE=case_d85c2f9b3487b1ea
make case-diagnose CASE=case_d85c2f9b3487b1ea; make case-draft CASE=case_d85c2f9b3487b1ea
make case-show CASE=case_d85c2f9b3487b1ea
make case-draft CASE=case_d85c2f9b3487b1ea TEMPLATE=appeal
make case-draft CASE=case_d85c2f9b3487b1ea TEMPLATE=no-such-template
# control file: drafting reply "Dear payer, here is the letter." (no JSON letter)
make case-draft CASE=case_d85c2f9b3487b1ea; make case-show CASE=case_d85c2f9b3487b1ea
# control file: drafting role unavailable
make case-draft CASE=case_d85c2f9b3487b1ea; make case-show CASE=case_d85c2f9b3487b1ea
make case-confirm CASE=case_d85c2f9b3487b1ea FIELD=claim_id VALUE=CLAIM-77; make case-show ...; make case-draft ...
make case-diagnose CASE=case_d85c2f9b3487b1ea; make case-draft CASE=case_d85c2f9b3487b1ea
make case-export CASE=case_d85c2f9b3487b1ea FORMAT=pdf TO=<scratch>/out71
make case-export CASE=case_d85c2f9b3487b1ea FORMAT=docx TO=<scratch>/out71
pdfinfo <scratch>/out71/*.pdf; pdftotext -layout <scratch>/out71/*.pdf -; textutil -convert txt -stdout <scratch>/out71/*.docx
qlmanage -t -s 900 -o <scratch>/out71 <scratch>/out71/*.pdf <scratch>/out71/*.docx
curl ... "http://127.0.0.1:18214/corpus/audit?profile=default&case_id=case_d85c2f9b3487b1ea"   # see Notes
```

```text
tests/test_us_7_1_appeal_draft.py .....................................  [100%]
- generated xml file: .../evidence/US-7.1/junit.xml -
===================== 37 passed, 1154 deselected in 4.62s ======================
test_us_7_1_draft_from_rule_card_and_template PASSED
test_us_7_1_draft_carries_review_label PASSED
test_us_7_1_template_chosen_by_denial_reason[...] PASSED (3 cases)
test_us_7_1_drafting_needs_a_current_diagnosis PASSED
test_us_7_1_no_letter_template PASSED
test_us_7_1_a_case_without_rule_cards_is_drafted PASSED
test_us_7_1_unusable_reply_stores_nothing[...] PASSED (5 cases)
test_us_7_1_drafting_model_missing PASSED
test_us_7_1_a_failed_draft_ends_with_its_code[...] PASSED (model_unavailable, case_closed, drafting_failed)
test_us_7_1_prompt_carries_letter_facts PASSED
test_us_7_1_draft_stale_after_confirmed_field PASSED
test_us_7_1_draft_again_replaces_the_draft PASSED
test_us_7_1_draft_purged_with_case PASSED
test_us_7_1_unedited_drafting_command_migrates PASSED
(37 in all, 0 failed)

junit-node.xml: 2 US-7.1 cases, fail 0
  test_us_7_1_pane_draft_from_rule_card_and_template
  test_us_7_1_pane_draft_carries_review_label
appeal_draft.test.mjs (whole file): ℹ tests 17  ℹ pass 17  ℹ fail 0

$ uv run pytest -m models -k us_7 -rA --no-cov -p no:cacheprovider
collected 1191 items / 1190 deselected / 1 selected
tests/test_us_7_1_appeal_draft.py .                                      [100%]
PASSED tests/test_us_7_1_appeal_draft.py::test_us_7_1_draft_real_model
===================== 1 passed, 1190 deselected in 43.02s ======================
$ lsof -nP -iTCP:18206 -sTCP:LISTEN
(no output, exit 1: nothing listening on 18206)

$ make case-draft CASE=case_d85c2f9b3487b1ea          # extracted, not diagnosed
curl: (22) The requested URL returned error: 409
error: not_diagnosed
make: *** [case-draft] Error 1
$ make case-diagnose CASE=case_d85c2f9b3487b1ea
classifying    0%
explaining    50%
done         100%
$ make case-draft CASE=case_d85c2f9b3487b1ea
drafting       0%
done         100%
$ make case-show CASE=case_d85c2f9b3487b1ea           (draft, text omitted here)
 "label": "draft for human review",
 "template_id": "appeal-prior-authorization",
 "rule_cards": ["ACME Health/appeal_levels", "ACME Health/required_docs"],
 "diagnosed_at": "2026-10-31T20:24:05.413689Z", "drafted_at": "2026-10-31T20:24:05.654111Z", "edited_at": null
draft_stale: False
--- text --- (the fake drafting reply, marker SYNTH-OPS-7; placeholders kept)
Re: Appeal of claim CLAIM-77, denied 2026-10-15
Patient: [Patient name], member ID [Member ID]
...
$ make case-draft CASE=case_d85c2f9b3487b1ea TEMPLATE=appeal
drafting       0%
done         100%
  draft: {'label': 'draft for human review', 'template_id': 'appeal', 'drafted_at': '2026-10-31T20:24:17.321081Z', 'edited_at': None} draft_stale: False
$ make case-draft CASE=case_d85c2f9b3487b1ea TEMPLATE=no-such-template
error: no_letter_template
$ make case-draft ...                                  (reply with no JSON letter)
drafting       0%
failed         0%  drafting_failed
  draft: {... 'template_id': 'appeal', 'drafted_at': '2026-10-31T20:24:17.321081Z' ...}   (previous draft kept)
$ make case-draft ...                                  (drafting role unavailable)
drafting       0%
failed         0%  model_unavailable
  draft: {... 'drafted_at': '2026-10-31T20:24:17.321081Z' ...}                           (previous draft kept)
$ make case-confirm ... FIELD=claim_id VALUE=CLAIM-77; make case-show ...
  draft_stale: True
$ make case-draft ...
error: not_diagnosed
$ make case-diagnose ...; make case-draft ...
drafting       0%
done         100%
  draft: {... 'template_id': 'appeal-prior-authorization', 'drafted_at': '2026-10-31T20:24:25.580227Z' ...} draft_stale: False

$ make case-export CASE=case_d85c2f9b3487b1ea FORMAT=pdf TO=<scratch>/out71
    "format": "pdf", "filename": "appeal-draft-case_d85c2f9b3487b1ea.pdf", "size_bytes": 34885,
    "expires_at": "2026-10-31T20:39:45.664593Z"
copied to <scratch>/out71/appeal-draft-case_d85c2f9b3487b1ea.pdf
$ pdfinfo ...pdf
Title:           Appeal letter (draft for human review)
Pages:           1
$ pdftotext -layout ...pdf -
Draft for human review
  [Practice address]
  ACME Health Plan, Appeals Unit
  Re: Appeal of claim CLAIM-77, denied 2026-10-15
$ textutil -convert txt -stdout ...docx
Draft for human review
[Practice address]
ACME Health Plan, Appeals Unit

audit (case_d85c2f9b3487b1ea): case_drafted 3 (the three completed drafts; the two failed runs
stored nothing), case_diagnosed 4, case_opened 6, field_confirmed 1; entries carry IDs and times only
worker log: 0 lines with "SYNTH-OPS-7", "CLAIM-77", "Appeals Unit", or "Practice address"
plaintext search of the scratch store (exports excluded): no file contains "SYNTH-OPS-7" or "Appeals Unit"
after the worker stopped: exports folder empty; port 18214 free
```

Artifacts: `evidence/US-7.1/junit.xml`, `evidence/US-7.1/junit-node.xml`

## Failures

None.

## Notes

- The real model: `test_us_7_1_draft_real_model` ran once against the real Ternary-Bonsai-2-27B in
  `~/Models`, through the `mtplx` venv, on 127.0.0.1:18206. It passed in 43 s. It asserts only that
  the letter contains `CLAIM-77` and has the label. I did not see the letter text, because the test
  does not print it. The following are UNVERIFIED for the real model: the letter's quality, whether
  it follows the template, and whether it keeps placeholders instead of inventing patient details.
  After the run, `lsof` showed nothing listening on 18206, and no ClaimCoach-started `mtplx`
  process remained. The test used a temporary `state_dir` and corpus. It did not touch
  `~/.hermes` or its `models.yaml`.
- Something unrelated to ClaimCoach was already running before this run: an `mtplx serve` of the
  same Bonsai 27B on 127.0.0.1:8080 (PID 91111, started Thu Oct 29 05:48 by a
  `copilot-detached-supervisor`). I left it running and did not touch it. It means two 27B
  instances were in memory during the real-model test. ClaimCoach's memory guard (BR-12) covers
  only ClaimCoach's own model servers, so it cannot see that process.
- The pane: the node tests render the pane under `register-fakes.mjs`. The pane was not seen in a
  live Hermes desktop.
- How the operator run was isolated: `serve_draft_worker.py` (in the session scratchpad, not the
  repo) served the real `create_app` with `HERMES_HOME` and `MODELS_HOME` set to a scratch
  directory and an `InMemoryKeyProvider` (no Keychain item). Four in-process `FakeModelServer`s
  stood in for embedding, classification, explanation, and drafting, on 127.0.0.1:18214 with
  `WORKER_PORT=18214`. All data was synthetic. The worker was stopped with SIGTERM afterwards,
  the exports folder was emptied, and port 18214 was free. The real `~/.hermes` was not touched.
  The `make` case targets call the worker directly. Gateway relaying is covered by the tests.
- `make corpus-audit CASE=…` printed `error: worker_unavailable` against this harness. That is
  expected, not a defect: since 13b88f3, the corpus CLI sends the token only to the port that the
  launcher recorded in the worker's PID file. The harness was not started by the launcher, so no
  PID file exists. I read the same audit through `GET /corpus/audit` with curl and the scratch
  token instead.
- The spec-delta scenarios (`openspec/changes/us-7-1-appeal-draft/specs/`) were exercised as
  follows:
  - "The template is chosen by the denial reason": `test_us_7_1_template_chosen_by_denial_reason`.
    In the operator run, the default draft chose `appeal-prior-authorization` and `TEMPLATE=appeal`
    chose `appeal`.
  - "An unusable reply stores nothing": `test_us_7_1_unusable_reply_stores_nothing`, and the
    operator run ended `drafting_failed` with the previous draft kept.
  - "A case that is not diagnosed": `test_us_7_1_drafting_needs_a_current_diagnosis`, and the
    operator run returned `not_diagnosed` both before diagnosis and after a confirmed field.
  - "No letter template on file": `test_us_7_1_no_letter_template`, and the operator run returned
    `no_letter_template` for an unknown `TEMPLATE`.
  - "An unedited earlier models.yaml is migrated": `test_us_7_1_unedited_drafting_command_migrates`.
    The user's real `models.yaml` was not opened.
  - "A confirmed field makes the draft stale": `test_us_7_1_draft_stale_after_confirmed_field`, and
    in the operator run `draft_stale` was True after `case-confirm`.
- A small runbook mismatch, outside this story's criteria: `appeal-drafting.md` says a failed
  `make case-draft` "exits 1". The recipe does exit 1 (`make: *** [case-draft] Error 1`), but
  `make` itself returns 2, which is what a calling shell sees.
