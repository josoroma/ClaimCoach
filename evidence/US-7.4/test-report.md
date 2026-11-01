# Test Report: US-7.4 Corrected Claim Draft

Change: us-7-4-corrected-claim-draft
Story: US-7.4
Verdict: pass
Coverage: 6/7 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24); no ClaimCoach worker running; the user's `~/.hermes/plugin-data/claimcoach/models.yaml` fails validation (`python -m claimcoach.models check`: `roles.embedding.command: unknown placeholder(s) ['claimcoach']`, same for `rerank`)

## Acceptance Criteria Evaluated

Rows 1 to 6 are the six PM-approved SPECS.md scenarios, run against the offline tests and an
operator run of `make case-correct` and `make case-correction-export` on a scratch loopback worker
over fake models. Row 7 is the same flow on the real drafting model, which was not run (see Notes).
The code changed while I was testing (see Notes). The results below are from the final run on the
code as of 04:36 local: all tests again, `make evidence`, and the whole operator flow a second
time (scratch run `run2`).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "An appeal-only denial gets a recommendation, not a corrected-claim draft: Then the pane recommends an appeal and shows why, and no corrected-claim draft is attached unless the biller asks for one" | PASS | `test_us_7_4_appeal_only_denial_gets_a_recommendation` and `test_us_7_4_routing_table_is_the_approved_one[...]` (12 cases, the approved table: medical_necessity, prior_authorization, timely_filing, non_covered_service go to appeal), `test_us_7_4_no_remedy_without_a_current_diagnosis`, the code splits (8 cases), and `test_us_7_4_rule_card_overrides_the_table` plus its end-to-end test pass. Node `test_us_7_4_pane_appeal_only_denial_gets_a_recommendation`: the pane shows "Recommended fix: an appeal." and "From ClaimCoach's table for this denial reason. You can draft either one.", shows no corrected-claim panel, and leaves **Draft corrected claim** enabled. Operator: a case pasted from a synthetic 835 with `CAS*CO*50`, classified medical_necessity, `make case-show` gave `remedy {"remedy": "appeal", "basis": "table", "denial_reason": "medical_necessity", ...}` and `correction None`. When I asked anyway, `make case-correct` ended `done 100%` with one claim-level `claim_data` change citing `CO-50` |
| 2 | "A correctable denial gets a list of changes for human review: Then a corrected-claim draft labeled \"draft for human review\" is attached to the case, and each change names a claim line or the claim, a field, an action, and the codes behind it" | PASS | `test_us_7_4_correctable_denial_gets_a_list_of_changes`, `test_us_7_4_the_prompt_holds_the_plan_as_data`, `test_us_7_4_changes_are_planned_by_fixed_rules`, `test_us_7_4_unprocessable_claim_is_new` (MA130 gives frequency 1), `test_us_7_4_label_is_always_present`, and the refusal tests (`not_diagnosed`, closed case, running job, no models) pass. Node: `test_us_7_4_pane_correctable_denial_gets_a_list_of_changes` and `test_us_7_4_pane_label_is_always_present`. Operator: a case pasted from the synthetic 835 with `CAS*CO*4*250~LQ*HE*M51~`, classified coding_error, diagnosed with codes `CO-4, M51`, remedy `corrected_claim` (basis `table`). Before it was diagnosed, `make case-correct` was refused with `not_diagnosed` (exit 2). After diagnosis it printed `drafting 0%` then `done 100%`. `make case-show` then had `correction` with `"label": "draft for human review"`, `original_claim_id` `CLAIM-77`, `frequency_code` `7`, and two changes: line 1 `modifier` (because `CO-4`) and line 1 `procedure_code` (because `CO-4, M51`), each with `action` and `why`. `make corpus-audit` showed `correction_drafted` and `correction_exported` entries holding only seq, time, action, case ID, and profile |
| 3 | "A value missing from the documents is never invented: Then that change's current value reads \"not in your documents\", and no change proposes a new procedure, diagnosis, or modifier code" | PASS | `test_us_7_4_value_missing_from_documents_is_never_invented`, `test_us_7_4_reply_that_proposes_a_code_is_refused[...]` (6 cases: modifier 59, modifiers -25, 99214, HCPCS G0438, E11.9, I10), `test_us_7_4_a_reply_may_repeat_what_the_documents_hold`, `test_us_7_4_unusable_replies_are_refused[...]` (7), `test_us_7_4_a_refused_reply_stores_nothing`, and `test_us_7_4_export_text_says_what_is_missing` pass. Node `test_us_7_4_pane_value_missing_from_documents_is_never_invented`. Operator: the `modifier` change has `"current_value": null`, and `procedure_code` has `99213`, copied from the extraction. The PDF and DOCX read "1. Line 1, modifier (current value: not in your documents)". Then I switched the fake drafting model to answer "Append modifier 59 to the line." and ran `make case-correct`: it printed `failed 0% correction_failed` (exit 2), and the stored correction kept its earlier `drafted_at` (`previous kept True`) |
| 4 | "A draft goes stale after re-extraction: Then the draft is marked stale and the pane offers to redraft it" | PASS | `test_us_7_4_draft_goes_stale_after_re_extraction` passes. Node `test_us_7_4_pane_draft_goes_stale_after_re_extraction`: the panel shows "The case changed since this draft was made; check it, or draft it again." and the button reads "Draft corrected claim again". Operator: `make case-confirm CASE=<id> FIELD=claim_id VALUE=CLAIM-77` returned `correction_stale True`, `diagnosis_stale True`, `remedy None`, with the correction kept. `make case-correct` was then refused with `not_diagnosed` (exit 2). After `make case-diagnose` and `make case-correct`, `make case-show` gave `correction_stale False` and remedy `corrected_claim` |
| 5 | "The corrected-claim draft exports as PDF or DOCX: Then a corrected-claim-draft-*.pdf or .docx file carrying the draft label is written" | PASS | `test_us_7_4_export_pdf_and_docx` and `test_us_7_4_the_pane_and_the_export_name_fields_alike` pass. Node: `test_us_7_4_pane_export_pdf_and_docx`, plus the refused, failed, and unsaved export cases. Operator: before any draft existed, `make case-correction-export CASE=<id> FORMAT=pdf` was refused with `not_corrected` ("Draft the corrected claim before exporting it.", exit 2). After the draft, `FORMAT=pdf TO=<scratch>/out` and `FORMAT=docx TO=<scratch>/out` printed `filename` `corrected-claim-draft-case_74282bec945a140c.pdf` (34997 bytes) and `.docx` (1900 bytes), then `copied to …`. The copies are mode 0600. The worker-side files are mode 0600 in a 0700 `exports/` folder. Exporting again to the same `TO` was refused with `… exists; choose another TO` (exit 2). `pdfinfo`: Title "Corrected claim (draft for human review)", 1 page, and the page's first line is "Draft for human review". `textutil`: the DOCX's first line is "Draft for human review". Both list the claim number, frequency code 7, and the two changes with their codes |
| 6 | "No submit control: Then neither [the corrected-claim route nor its pane control] sends, submits, or transmits anything (US-7.3)" | PASS | `test_us_7_4_no_submit_control` passes. All 26 US-7.3 pins pass: `test_us_7_3_no_transmitting_route` pins `POST /cases/{case_id}/correction` and `POST /cases/{case_id}/correction/export` on both the gateway and the worker tables. `test_us_7_3_case_routes_reach_only_loopback` runs `correction` and `correction/export` end to end and sees only loopback connects. `test_us_7_3_http_clients_only_in_loopback_modules` also passes. Node: `test_us_7_4_pane_no_submit_control` and `test_us_7_3_no_send_contribution` pass (whole `appeal_draft.test.mjs` and `corrected_claim.test.mjs`: 31 of 31). My own check: `grep -i -E "send\|submit\|fax\|e-?mail\|transmit\|deliver\|portal\|clearinghouse" plugin/desktop/plugin.js` matched only header and doc comments stating the rule, and the internal `addDocument(..., send)` parameter. No `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `window.open`, `mailto:`, or `http(s)://` is in `plugin.js`. In `plugin/claimcoach/corrections/`, `httpx` is imported only as the type of an injected test transport, and the model call goes through the shared loopback `chat_completion` |
| 7 | "A correctable denial gets a list of changes for human review" with the real drafting model (Ternary-Bonsai-2-27B) on this Mac | UNVERIFIED | Not run. No ClaimCoach worker runs on this Mac, the user's `models.yaml` fails validation, and some model weights are missing under `~/Models`. No `models`-marked US-7.4 test exists (the `make test-models` set has none for corrections). How the real model's action and why text holds up against the code-shape parser is not measured |

## Evidence Commands

```bash
make test-story STORY=US-7.4
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_7_4 or us_7_3" -v
node --import ./plugin/desktop/tests/register-fakes.mjs --test \
  plugin/desktop/tests/corrected_claim.test.mjs plugin/desktop/tests/appeal_draft.test.mjs
make evidence STORY=US-7.4
grep -n -i -E "send|submit|fax|e-?mail|transmit|deliver|portal|clearinghouse" plugin/desktop/plugin.js
grep -n -E "fetch\(|XMLHttpRequest|WebSocket|sendBeacon|window\.open|openExternal|mailto:|https?://" plugin/desktop/plugin.js
uv run python -m claimcoach.models check          # the user's real models.yaml: fails (pre-existing)
# Operator run (run_flow.sh in the session scratchpad). serve_correction_worker.py serves
# tests/fakes/evals.eval_worker (real create_app and CorpusService, ACME rule cards and code notes,
# fake model servers) on 127.0.0.1:18218, started with " -m claimcoach.worker " in its argv. The
# classifier answers the reason in a control file, and the drafting role is
# tests/fakes/corrections.drafting_responder (or, in "code" mode, an action naming modifier 59).
# Token and worker.json are written under the scratch HERMES_HOME. ~/.hermes is not touched.
export HERMES_HOME=<scratch>/run2/hermes MODELS_HOME=<scratch>/run2/models WORKER_PORT=18218
# <scratch>/era.835 = tests.test_us_7_4_corrected_claim.era("CAS*CO*4*250~LQ*HE*M51~")
make case-new; make case-paste CASE=case_74282bec945a140c FILE=<scratch>/era.835
make case-correct CASE=case_74282bec945a140c                       # before diagnosis
make case-correction-export CASE=case_74282bec945a140c FORMAT=pdf  # before a draft
make case-process CASE=case_74282bec945a140c; make case-diagnose CASE=case_74282bec945a140c
make case-show CASE=case_74282bec945a140c
make case-correct CASE=case_74282bec945a140c; make case-show CASE=case_74282bec945a140c
make case-correction-export CASE=case_74282bec945a140c FORMAT=pdf TO=<scratch>/run2/out
make case-correction-export CASE=case_74282bec945a140c FORMAT=docx TO=<scratch>/run2/out
make case-correction-export CASE=case_74282bec945a140c FORMAT=pdf TO=<scratch>/run2/out   # again
pdfinfo <scratch>/run2/out/*.pdf; pdftotext -layout <scratch>/run2/out/*.pdf -
textutil -convert txt -stdout <scratch>/run2/out/*.docx
# control: drafting "code" (action "Append modifier 59 to the line.")
make case-correct CASE=case_74282bec945a140c; make case-show CASE=case_74282bec945a140c
make case-confirm CASE=case_74282bec945a140c FIELD=claim_id VALUE=CLAIM-77
make case-correct CASE=case_74282bec945a140c      # diagnosis now stale
make case-diagnose CASE=case_74282bec945a140c; make case-correct CASE=case_74282bec945a140c
# control: reason medical_necessity; <scratch>/era_mn.835 = era("CAS*CO*50*250~")
make case-new; make case-paste CASE=case_acda59b83aa4a75f FILE=<scratch>/era_mn.835
make case-process ...; make case-diagnose ...; make case-show ...; make case-correct ...
make corpus-audit CASE=case_74282bec945a140c
# run3 (fresh scratch home): draft, case-confirm, then export the stale draft
make case-correction-export CASE=case_70517acdbf9523e2 FORMAT=pdf TO=<scratch>/run3/out   # and docx
pdftotext -layout <scratch>/run3/out/*.pdf - | grep -i -E "stale|changed|check it"
grep -rl -a "Check this field against|The payer's codes on this line" <scratch>/run2/hermes <scratch>/run2/worker.out
```

```text
$ make test-story STORY=US-7.4
(pytest part, final run: 77 passed)
▶ US-7.4 an appeal-only denial gets a recommendation, not a corrected-claim draft
  ✔ test_us_7_4_pane_appeal_only_denial_gets_a_recommendation
  ... (7 suites, each ✔)
ℹ tests 19  ℹ pass 19  ℹ fail 0

$ uv run pytest ... -k "us_7_4 or us_7_3"          # final run, code as of 04:36
103 passed, 1677 deselected in 4.78s

$ node ... corrected_claim.test.mjs appeal_draft.test.mjs
  ✔ test_us_7_3_no_send_contribution
ℹ tests 31  ℹ pass 31  ℹ fail 0

$ make evidence STORY=US-7.4                        # 04:36:41, exit 0
===================== 77 passed, 1703 deselected in 3.99s ======================
evidence/US-7.4/junit.xml: 77 testcases, 0 failures
evidence/US-7.4/junit-node.xml: 19 testcases, 0 failures

$ make case-correct CASE=case_74282bec945a140c      # before diagnosis
curl: (22) The requested URL returned error: 409
error: not_diagnosed
make: *** [case-correct] Error 1
$ make case-correction-export CASE=case_74282bec945a140c FORMAT=pdf
{"ok":false,"error":{"code":"not_corrected","message":"Draft the corrected claim before exporting it."}}
make: *** [case-correction-export] Error 1

$ make case-show ...                                # after process and diagnose
diagnosis coding_error ['CO-4', 'M51'] stale False
remedy {"remedy": "corrected_claim", "basis": "table", "denial_reason": "coding_error", "codes": [], "rule_card": null}
correction None correction_stale False

$ make case-correct CASE=case_74282bec945a140c
drafting       0%
done         100%
$ make case-show ...   (correction)
  "label": "draft for human review",
  "original_claim_id": "CLAIM-77",
  "frequency_code": "7",
  "corrections": [
    {"line": 1, "field": "modifier", "current_value": null, "because": ["CO-4"], "action": "...", "why": "..."},
    {"line": 1, "field": "procedure_code", "current_value": "99213", "because": ["CO-4", "M51"], "action": "...", "why": "..."}
  ],
  "omitted": 0,
  "rule_cards": ["ACME Health/appeal_levels", "ACME Health/required_docs"],
correction_stale False

$ make case-correction-export CASE=case_74282bec945a140c FORMAT=pdf TO=<scratch>/run2/out
    "filename": "corrected-claim-draft-case_74282bec945a140c.pdf",
    "size_bytes": 34997,
copied to <scratch>/run2/out/corrected-claim-draft-case_74282bec945a140c.pdf
$ make case-correction-export ... FORMAT=docx TO=<scratch>/run2/out
    "filename": "corrected-claim-draft-case_74282bec945a140c.docx",
    "size_bytes": 1900,
$ make case-correction-export ... FORMAT=pdf TO=<scratch>/run2/out      # again
<scratch>/run2/out/corrected-claim-draft-case_74282bec945a140c.pdf exists; choose another TO
make: *** [case-correction-export] Error 2
-rw------- 1900 corrected-claim-draft-case_74282bec945a140c.docx
-rw------- 34997 corrected-claim-draft-case_74282bec945a140c.pdf
drwx------ exports dir

$ pdfinfo / pdftotext -layout
Title:           Corrected claim (draft for human review)
Pages:           1
Draft for human review
  Corrected claim: draft for human review
  Original claim number: CLAIM-77
  Claim frequency code: 7 (a replacement of the prior claim)
  Make and check these changes in your billing system. ClaimCoach does not send, submit,
  or file claims; nothing here leaves this Mac.
  1. Line 1, modifier (current value: not in your documents)
  Codes: CO-4
  2. Line 1, procedure code (current value: 99213)
  Codes: CO-4, M51
  Drafted 2026-11-01 for human review.
$ textutil -convert txt -stdout *.docx
Draft for human review
Corrected claim: draft for human review
...

$ make case-correct ...                             # drafting reply names modifier 59
drafting       0%
failed         0%  correction_failed
make: *** [case-correct] Error 1
previous kept True 2026-11-01T10:37:21.701871Z

$ make case-confirm CASE=case_74282bec945a140c FIELD=claim_id VALUE=CLAIM-77
correction_stale True diagnosis_stale True remedy None correction kept True
$ make case-correct ...
error: not_diagnosed
make: *** [case-correct] Error 1
$ make case-diagnose ...; make case-correct ...; make case-show ...
after redraft: correction_stale False remedy corrected_claim

$ (appeal-only case case_acda59b83aa4a75f, CAS*CO*50, medical_necessity)
diagnosis medical_necessity ['CO-50']
remedy {"remedy": "appeal", "basis": "table", "denial_reason": "medical_necessity", "codes": [], "rule_card": null}
correction None
$ make case-correct ...                             # the biller asks anyway
done         100%
label draft for human review [(None, 'claim_data', None, ['CO-50'])]

$ make corpus-audit CASE=case_74282bec945a140c       (correction entries)
{"seq": 7, "at": "2026-11-01T10:37:21.702095Z", "action": "correction_drafted", "case_id": "case_74282bec945a140c", "profile": "default"}
{"seq": 9, "at": "2026-11-01T10:37:22.170380Z", "action": "correction_exported", "case_id": "case_74282bec945a140c", "profile": "default"}
{"seq": 10, "at": "2026-11-01T10:37:22.421106Z", "action": "correction_exported", "case_id": "case_74282bec945a140c", "profile": "default"}
{"seq": 15, "at": "2026-11-01T10:37:23.727727Z", "action": "correction_drafted", "case_id": "case_74282bec945a140c", "profile": "default"}

$ grep -rl -a "<the fake's action and why text>" <scratch>/run2/hermes <scratch>/run2/worker.out
(no match)

$ uv run python -m claimcoach.models check
error: models.yaml: roles.embedding.command: unknown placeholder(s) ['claimcoach']; allowed: ['host', 'logs', 'model', 'port', 'venv']
```

Artifacts: `evidence/US-7.4/junit.xml`, `evidence/US-7.4/junit-node.xml`

## Failures

None.

## Notes

- Row 7 (the real drafting model) is UNVERIFIED. No ClaimCoach worker runs on this Mac, and the
  user's `models.yaml` fails validation (the existing `{claimcoach}` placeholder problem). Some
  weights are missing under `~/Models`, and US-7.4 has no `models`-marked test. As instructed, I
  did not start the real worker, download models, edit `models.yaml`, or touch `~/.hermes`.
- The checkout changed while I was testing. My first operator run (04:33 to 04:35) was on earlier
  code. After it, `plugin/claimcoach/corrections/draft.py`, `corrections/types.py`,
  `letters/export.py`, `agent/types.py`, `plugin/desktop/plugin.js`, and both US-7.4 test files
  changed (04:35 to 04:36). The Python US-7.4 test count went from 62 to 77, and the case view
  gained `omitted`. One `make evidence` run during those edits failed in its node step. Run
  directly a minute later, the node tests passed, and `make evidence` then exited 0 (04:36:41).
  I then re-ran every test and the whole operator flow on a fresh scratch home (`run2`). This
  report records only that final run. Afterwards only `docs/runbooks/appeal-drafting.md` and the
  OpenSpec `design.md` changed, not code or tests.
- Rows 1 to 6 ran on fake models. They test the routing table, the fixed change plan, the code
  parser, staleness, export, and the routes, not real model output. The scratch worker
  (`serve_correction_worker.py`) is the real `create_app` over `tests/fakes/evals.eval_worker`,
  with two responders swapped in from control files. "Shows why" in the pane (row 1) and "offers
  to redraft" (row 4) are checked by the node tests. The operator commands show what decided the
  remedy (`basis`, `denial_reason`) and `correction_stale`.
- Observation: the corrected-claim draft's `rule_cards` list the payer's `appeal_levels` and
  `required_docs` cards (the ACME fixture has no `corrected_claims` card). The PDF and DOCX print
  them as "Payer rule cards used". The design allows this, but a biller may find appeal-level
  cards on a corrected claim odd.
- Observation: a stale corrected-claim draft can still be exported. In scratch run `run3`, on the
  final code, `make case-correction-export` wrote both the PDF and the DOCX after `case-confirm`
  had set `correction_stale` to true. The pane keeps **Export corrected claim PDF/DOCX** enabled
  for a stale draft too (`disabled: current.state !== 'ready'`), though it shows the stale
  warning next to them. Neither file says the draft is stale: `pdftotext` and `textutil` found no
  "stale" or "changed". Neither SPECS.md nor the change spec asks for a stale export to be
  refused, so this is not a FAIL. A copied file has no warning once it leaves the pane.
- Exports in the scratch homes expire on their own, and the scratch worker was stopped after each
  run.

## Implementer follow-up (2026-11-01, after this run)

Both observations above were acted on after the tester's final run, and the review's findings
were fixed (see `openspec/changes/archive/2026-11-01-us-7-4-corrected-claim-draft/review.md`):

- A stale corrected-claim draft still exports, and its PDF and DOCX now open with "OUT OF DATE:
  the case changed after this draft was made" (`test_us_7_4_draft_goes_stale_after_re_extraction`
  asserts it, and that a fresh draft's file does not).
- The export's line now reads "Payer rule cards on file when drafted" (the cards the model was
  given), instead of "Payer rule cards used".

`make evidence STORY=US-7.4` was re-recorded after these changes (`junit.xml`, `junit-node.xml`,
0 failures), and `make verify` passed (1766 passed, 100% Python and pane coverage, `ok US-7.4`).
The real-model row stays UNVERIFIED for the reasons above.
