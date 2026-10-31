# Test Report: US-6.1 Denial Classification and Appeal Likelihood

Change: us-6-1-denial-classification
Story: US-6.1
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; Qwen3-8B-4bit and Qwen3-14B-4bit weights absent

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Classification returns a typed result: Then the result validates against the typed Diagnosis model with a denial reason and an appeal likelihood of low, medium, or high" | PASS | Exercised by the offline pipeline with a fake classification model. The real model is UNVERIFIED: `test_us_6_1_classification_real_model` (marked `models`) was SKIPPED because the Qwen3-8B weights are not at `~/Models/Qwen3-8B-4bit`. `test_us_6_1_classification_typed_result`: a pasted 835 case goes through the gateway router to the worker, is extracted, and is then diagnosed (`kind == "diagnose"`). The opened case's diagnosis has `denial_reason` `DenialReason.PRIOR_AUTHORIZATION` and `appeal_likelihood` `AppealLikelihood.HIGH` (one of low, medium, high), `codes == ["CO-197", "N286"]`, an `extraction_digest` equal to the extraction's digest, and `diagnosis_stale` false. It round-trips through `Diagnosis.model_validate_json`, two `case_diagnosed` entries are audited, and the last event is `done`. `test_us_6_1_label_set_is_closed_and_guided`: exactly the 11 labels, each one explained in the template. `test_us_6_1_diagnosis_model_is_strict`: 0 or 6 reasons, `certain`, `fraud`, a bad code, a bad digest, a naive timestamp, and an extra key are each refused. `test_us_6_1_reply_outside_closed_set_fails`: a `fraud` reply ends `failed`/`diagnosis_failed` and the previous diagnosis stays. `test_us_6_1_unusable_replies_are_refused[...]` (9 cases). `test_us_6_1_prompt_carries_only_facts`: one request through the registered `classification` template, with the case facts and the code notes in data blocks. The claim number, dates, and names are withheld, and the request uses temperature 0.0 and max_tokens 1024. Operator: on an extracted case, `make case-diagnose` printed `classifying 0%`, `explaining 50%`, `done 100%`, and `make case-show` showed `"denial_reason": "prior_authorization"`, `"appeal_likelihood": "high"`, `"codes": ["CO-197", "N286"]`, and `"diagnosis_stale": false`. When the fake answered `denial_reason` `fraud`, the run printed `failed 0% diagnosis_failed` (make Error 1), and `make case-show` kept the previous diagnosis (same `diagnosed_at`). Refusal: `make case-diagnose` on a case that was never processed gave 409 `error: not_extracted`, both with no documents and with a pasted 835. An unknown case gave 404 `case_not_found` |
| 2 | "Appeal likelihood includes reasons: Then the appeal likelihood is shown with at least one reason" | PASS | `test_us_6_1_likelihood_includes_reasons`: the opened case's `likelihood_reasons` has at least 1 entry and equals the model's two reasons. Pane (node): `test_us_6_1_pane_likelihood_includes_reasons`: the panel labelled `Diagnosis` renders "Denial reason: Prior authorization or referral", "Codes: CO-197, N286", "Appeal likelihood: High", and a list holding both reasons (length at least 1). A current diagnosis shows no stale note. A diagnosis without reasons cannot be stored: `test_us_6_1_diagnosis_model_is_strict` refuses `likelihood_reasons: []`, and `test_us_6_1_unusable_replies_are_refused` refuses missing, empty, blank, or non-list reasons. Operator: `make case-show` printed `"appeal_likelihood": "high"` with two `likelihood_reasons` ("The payer denied the line for a missing authorization (CO-197).", "Payers often accept a retroactive authorization with the medical records."). The reasons are canned by the fake model, so the reasons the real Qwen3-8B would give are UNVERIFIED |

## Evidence Commands

```bash
make evidence STORY=US-6.1
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_6_1 or us_6_2 or us_6_3" -v
uv run pytest -m models -k "us_6" -rs --no-cov -p no:cacheprovider
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_6_ plugin/desktop/tests/
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/case_diagnosis.test.mjs
# operator run against a scratch worker (serve_case_worker.py: real create_app, InMemoryKeyProvider,
# fake embedding, classification, and explanation servers; token in $HERMES_HOME/.../worker/token, 0600)
HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models .venv/bin/python -W ignore serve_case_worker.py --port 18213 --control <scratch>/control.json &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18213
make corpus-import FILE=<scratch>/rules.yaml        # see Notes: the corpus CLI ignores WORKER_PORT
python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml
make case-new
make case-diagnose CASE=case_3f9889c31823f1b7       # no documents, never processed
make case-paste CASE=case_3f9889c31823f1b7 FILE=<scratch>/era.835
make case-diagnose CASE=case_3f9889c31823f1b7       # 835 pasted, never processed
make case-process CASE=case_3f9889c31823f1b7
make case-diagnose CASE=case_3f9889c31823f1b7
make case-show CASE=case_3f9889c31823f1b7
make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=2026-10-20
make case-show CASE=case_3f9889c31823f1b7; make case-diagnose CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
# control file: the classification fake answers denial_reason "fraud"
make case-diagnose CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
make case-diagnose CASE=case_0000000000000000
python corpus_cli_on_port.py 18213 corpus audit --case case_3f9889c31823f1b7
```

```text
tests/test_us_6_1_diagnosis.py ....................................      [100%]
- generated xml file: .../evidence/US-6.1/junit.xml -
===================== 36 passed, 1047 deselected in 2.44s ======================

test_us_6_1_diagnosis.py::test_us_6_1_classification_typed_result PASSED
test_us_6_1_diagnosis.py::test_us_6_1_likelihood_includes_reasons PASSED
test_us_6_1_diagnosis.py::test_us_6_1_reply_outside_closed_set_fails PASSED
test_us_6_1_diagnosis.py::test_us_6_1_no_diagnosis_is_stored_for_a_bad_reply PASSED
test_us_6_1_diagnosis.py::test_us_6_1_unusable_replies_are_refused[...] PASSED (9 cases)
test_us_6_1_diagnosis.py::test_us_6_1_label_set_is_closed_and_guided PASSED
test_us_6_1_diagnosis.py::test_us_6_1_diagnosis_model_is_strict PASSED
test_us_6_1_diagnosis.py::test_us_6_1_prompt_carries_only_facts PASSED
test_us_6_1_diagnosis.py::test_us_6_1_diagnosis_requires_extraction PASSED
test_us_6_1_diagnosis.py::test_us_6_1_progress_relayed PASSED
test_us_6_1_diagnosis.py::test_us_6_1_one_job_per_case PASSED
test_us_6_1_diagnosis.py::test_us_6_1_a_failed_diagnosis_ends_with_its_code[...] PASSED (4 cases)
test_us_6_1_diagnosis.py::test_us_6_1_confirmed_field_makes_diagnosis_stale PASSED
test_us_6_1_diagnosis.py::test_us_6_1_diagnose_during_first_extraction_joins_it PASSED
test_us_6_1_diagnosis.py::test_us_6_1_case_items_check_migrates PASSED
test_us_6_1_diagnosis.py::test_us_6_1_failed_migration_leaves_the_store_as_it_was PASSED
test_us_6_1_diagnosis.py::test_us_6_1_diagnosis_purged_with_case PASSED
====================== 88 passed, 995 deselected in 5.47s ====================== (us_6_1, us_6_2, us_6_3)

junit-node.xml: 3 US-6.1 cases, fail 0
  ✔ test_us_6_1_pane_likelihood_includes_reasons (2.377166ms)
  ✔ test_us_6_1_pane_diagnoses_after_extraction (2.33325ms)
  ✔ test_us_6_1_pane_flags_stale_diagnosis (0.232875ms)
case_diagnosis.test.mjs (whole file): ℹ tests 28  ℹ pass 28  ℹ fail 0

$ uv run pytest -m models -k "us_6" -rs --no-cov -p no:cacheprovider
SKIPPED [1] tests/test_us_6_1_diagnosis.py:772: Qwen3-8B weights not found at /Users/josoroma/Models/Qwen3-8B-4bit
SKIPPED [1] tests/test_us_6_2_explanation.py:594: Qwen3-14B weights not found at /Users/josoroma/Models/Qwen3-14B-4bit
SKIPPED [1] tests/test_us_6_2_explanation.py:637: classification weights not found at /Users/josoroma/Models/Qwen3-8B-4bit
===================== 3 skipped, 1080 deselected in 2.42s ======================

$ make corpus-import FILE=<scratch>/rules.yaml
error: worker_unavailable
make: *** [corpus-import] Error 1
$ python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml
imported 3 code, 2 rule_card (5 chunks)
$ make case-new
    "case_id": "case_3f9889c31823f1b7", "documents": [], "extraction": null, "diagnosis": null,
    "diagnosis_stale": false, "deadline": null
$ make case-diagnose CASE=case_3f9889c31823f1b7       (no documents, never processed)
curl: (22) The requested URL returned error: 409
error: not_extracted
make: *** [case-diagnose] Error 1
$ make case-paste CASE=case_3f9889c31823f1b7 FILE=<scratch>/era.835
    "kind": "edi_835", "size_bytes": 456
$ make case-diagnose CASE=case_3f9889c31823f1b7       (835 pasted, never processed)
curl: (22) The requested URL returned error: 409
error: not_extracted
make: *** [case-diagnose] Error 1
$ make case-process CASE=case_3f9889c31823f1b7
extracting     0%
extracting    95%
done         100%
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7
 "diagnosis": {
  "denial_reason": "prior_authorization",
  "appeal_likelihood": "high",
  "likelihood_reasons": [
   "The payer denied the line for a missing authorization (CO-197).",
   "Payers often accept a retroactive authorization with the medical records."
  ],
  "codes": ["CO-197", "N286"],
  "extraction_digest": "a14ccab5c7b0f2894124e0728051f25e4f0b3491fc0b3e1e14e5a223076948b2",
  "diagnosed_at": "2026-10-31T18:27:50.653916Z", ... },
 "diagnosis_stale": false
$ make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=2026-10-20
denial_date: {'value': '2026-10-20', 'status': 'confirmed'} diagnosis_stale: True  diagnosis kept: True
$ make case-show CASE=case_3f9889c31823f1b7
diagnosis_stale: True
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7
diagnosis_stale: False
# fake classification model answers {"denial_reason": "fraud", "appeal_likelihood": "high", "reasons": [...]}
$ make case-show (before)  diagnosis: prior_authorization high diagnosed_at 2026-10-31T18:28:22.990729Z
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
failed         0%  diagnosis_failed
make: *** [case-diagnose] Error 1
$ make case-show (after)   diagnosis: prior_authorization high diagnosed_at 2026-10-31T18:28:22.990729Z
$ make case-diagnose CASE=case_0000000000000000
curl: (22) The requested URL returned error: 404
error: case_not_found
make: *** [case-diagnose] Error 1
$ corpus audit --case case_3f9889c31823f1b7
action counts: case_created 1, document_added 1, case_extracted 1, field_confirmed 1,
               case_diagnosed 9, case_opened 12          (IDs and times only)

# worker log (whole file besides the harness's control lines):
serving on 127.0.0.1:18213
diagnose job failed: ModelUnavailableError
diagnose job failed: DiagnosisFailedError
# plaintext search of the scratch user store: CLAIM-77: 0  ACME HEALTH: 0  prior_authorization: 0
#   "The authorization was not requested": 0  "Payers often accept": 0
```

Artifacts: `evidence/US-6.1/junit.xml`, `evidence/US-6.1/junit-node.xml`

## Failures

None.

## Notes

- The real model in rows 1 and 2: `test_us_6_1_classification_real_model` is marked `models` and was
  SKIPPED because `~/Models/Qwen3-8B-4bit` is absent. No model was downloaded. How Qwen3-8B
  labels the synthetic CO-197 / N286 case, and the reasons it would give, are UNVERIFIED. What
  exercised the scenarios is the offline pipeline. It uses the real 835 extraction, the real
  `classification` prompt template, real reply parsing, real `Diagnosis` validation, storage, and
  the gateway relay, with a canned reply from a fake OpenAI-compatible server.
- The pane: the node tests render the pane under `register-fakes.mjs` (fake React and fake host
  `ctx`). The diagnosis panel was not seen in a live Hermes desktop. `junit-node.xml` holds only
  the `test_us_6_1_*` pane tests, because the evidence target filters by name. The rest of
  `case_diagnosis.test.mjs`, which holds the review regressions, passed when I ran the whole file
  (28/28).
- The spec-delta scenarios (`openspec/changes/us-6-1-denial-classification/specs/case-diagnosis/spec.md`)
  were exercised as follows:
  - "A reply outside the closed set": `test_us_6_1_reply_outside_closed_set_fails`,
    `test_us_6_1_no_diagnosis_is_stored_for_a_bad_reply`, and the operator `fraud` run.
  - "Diagnosis before extraction": `test_us_6_1_diagnosis_requires_extraction` (409
    `not_extracted`, nothing relayed, no job; also 404, 422, and 409 `case_closed`), and the
    operator refusals.
  - "Diagnosis requested during the first extraction": `test_us_6_1_diagnose_during_first_extraction_joins_it`,
    `test_us_6_1_one_job_per_case`, and the pane test "a diagnosis joining a running extraction
    follows it as an extraction". This was not exercised by the operator run, because the 835 path
    extracts too fast to overlap.
  - "The pane diagnoses after extraction": `test_us_6_1_pane_diagnoses_after_extraction`
    (exactly one `/diagnose` call; the events arrive through `ctx.onEvent`, and the host is never
    touched), and "afterExtraction alone diagnoses a fully read case".
  - "Fields to confirm wait for the biller": the pane tests "fields left to confirm wait for the
    biller before any diagnosis" and "Diagnose case starts a diagnosis and explains a refusal".
  - "A diagnosis that fails before its start is answered": "a chained diagnosis that ends before
    its start is answered still ends the wait", "Diagnose case follows its own job before the
    start is answered", and "a failed diagnosis reopens the case with its fixed explanation".
  - "A confirmed field makes the diagnosis stale": `test_us_6_1_confirmed_field_makes_diagnosis_stale`,
    `test_us_6_1_pane_flags_stale_diagnosis`, and the operator run (`diagnosis_stale` was True
    after `case-confirm` and False after `case-diagnose`).
- The SPECS open question ("the closed set of denial-reason labels") is resolved in the spec delta
  as 11 labels. `test_us_6_1_label_set_is_closed_and_guided` checks the set.
- How the operator run was isolated: `serve_case_worker.py` (in the session scratchpad, not the
  repo) served the real `create_app` with `HERMES_HOME` and `MODELS_HOME` set to a scratch
  directory, an `InMemoryKeyProvider` (no Keychain item), and three in-process
  `FakeModelServer`s, on 127.0.0.1:18213 with `WORKER_PORT=18213`. Its control file switched the
  classification reply to `fraud`, and it took the explanation role away for the US-6.2 run. All
  data was synthetic: `ERA_835` and a synthetic "ACME Health" bundle. The worker and fakes were
  stopped afterwards, and port 18213 was confirmed free. The real `~/.hermes` was not touched.
  The `make` targets call the worker directly, and gateway relaying is covered by the tests.
- The audit count: case A was diagnosed six times. Four runs completed with 2 entries each, one
  failed while explaining with 1 entry, and the `fraud` run stored nothing with 0 entries, so
  there are 9 `case_diagnosed` entries. One of the completed runs was my first attempt to switch
  the fake to `fraud`. The helper that writes the control file failed to import `claimcoach`
  under the system `python3`, so the file stayed `{}` and that run used the normal reply. I
  repeated the step with the project venv. Only the repeated run is reported above as the
  `diagnosis_failed` evidence.
- Something I noticed, outside this story's criteria: `make corpus-import` and `make corpus-list`
  do not follow `WORKER_PORT`. `claimcoach.cli._client()` builds `WorkerConfig(data_dir=...)`, whose
  port is always 18200, so with `WORKER_PORT=18213` both returned `error: worker_unavailable`.
  I checked the CLI's resolved URL (`http://127.0.0.1:18200`) and token path (the scratch token
  was found). To load the bundle, `corpus_cli_on_port.py` ran the same `build_parser()` and
  `run()` with only the client's base URL changed. With the default port, `make start` and the
  corpus targets agree.
