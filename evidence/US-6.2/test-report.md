# Test Report: US-6.2 Plain-Language Explanation and Missing-Documentation Checklist

Change: us-6-2-explanation-checklist
Story: US-6.2
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; Qwen3-8B-4bit and Qwen3-14B-4bit weights absent

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Explanation and root cause are shown: Then the case shows a plain-language explanation and a likely root cause" | PASS | Exercised by the offline pipeline with fake classification and explanation models. The real model is UNVERIFIED: `test_us_6_2_explanation_real_model` and `test_us_6_2_diagnosis_real_models` (marked `models`) were SKIPPED because `~/Models/Qwen3-14B-4bit` and `~/Models/Qwen3-8B-4bit` are absent. `test_us_6_2_explanation_and_root_cause_shown`: after diagnosis with ACME Health's rule cards, the opened case's `diagnosis.explanation.explanation` and `.root_cause` equal the explanation model's reply, and the classification (`prior_authorization`) is kept. `test_us_6_2_prompt_carries_cards_and_numbered_documents`: there is one request to the `explanation` role through the registered `explanation` template. Its system prompt asks for plain language without unexplained jargon, and its data blocks are `case_facts`, `classification`, `code_notes`, `rule_cards`, and `required_documents`, with the documents numbered 1 to 4. The claim number, dates, and other payers' cards are withheld, and the request uses temperature 0.0 and max_tokens 1536. `test_us_6_2_unusable_explanations_are_refused[...]` (4 cases), `test_us_6_2_long_text_is_clipped_not_refused`. `test_us_6_2_progress_relayed`: the events are `classifying 0.0`, `explaining 0.5`, `done 1.0`, and none carries the explanation, the checklist, or the payer. Pane (node): `test_us_6_2_pane_explanation_and_root_cause_shown` checks that the `Explanation` section renders the explanation text and "Likely root cause: The authorization was not requested before the visit." Operator: `make case-diagnose` printed `classifying 0%`, `explaining 50%`, `done 100%`, and `make case-show` showed `explanation` and `root_cause` under `diagnosis` |
| 2 | "Checklist lists missing documentation: Then the case shows a checklist of missing documentation items drawn from the rule card's required documents" | PASS | `test_us_6_2_checklist_lists_missing_docs`: the model chose items 3 and 1. The case's checklist is document 1 then document 3, in the card's order and wording, with the model's `why`, and every item is one of ACME Health's 4 documents. `rule_cards` names `ACME Health/appeal_levels` and `ACME Health/required_docs` with their source, `verified_on` (today minus 30 days), and `stale` false. The shorter `ACME` card and the `Other Payer` card in the same corpus are not used. `test_us_6_2_items_off_the_card_dropped`: items 9 and 0, a repeat, `"3"`, `true`, a free-text document, and junk are dropped, and the result is documents 1, 2, and 4. `test_us_6_2_no_valid_item_lists_every_document[...]` (4 cases): all 4 documents are listed without a reason. `test_us_6_2_checklist_from_item_numbers`, `test_us_6_2_required_documents_round_trip`, `test_us_6_2_list_on_another_topic_refused` (422 `invalid_request`, nothing stored), `test_us_6_2_payer_cards_match_by_whole_words`, `test_us_6_2_two_spellings_are_one_payer`, `test_us_6_2_stale_card_is_flagged`, `test_us_6_2_corpus_list_shows_required_documents`. Pane (node): `test_us_6_2_pane_checklist_lists_missing_docs` checks the `Missing documentation` heading and two list items, "Copy of the denial notice or remittance: The appeal must cite it." and "Medical records for the date of service". The cards are listed with their verified dates and a stale suffix. Operator: the corpus import printed `imported 3 code, 2 rule_card (5 chunks)`, and the corpus list showed `ACME Health/required_docs ... (4 required documents)`. `make case-show` showed a checklist of "Copy of the denial notice or remittance" (why "The appeal must cite the denial.") and "Medical records for the date of service" (why "Shows the visit was medically necessary."), and `rule_cards` with both ACME Health cards (`verified_on` 2026-09-15, `stale` false). Which items the real Qwen3-14B would choose is UNVERIFIED |

## Evidence Commands

```bash
make evidence STORY=US-6.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_6_1 or us_6_2 or us_6_3" -v
uv run pytest -m models -k "us_6" -rs --no-cov -p no:cacheprovider
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_6_ plugin/desktop/tests/
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/case_diagnosis.test.mjs
# operator run against a scratch worker (serve_case_worker.py: real create_app, InMemoryKeyProvider,
# fake embedding, classification, and explanation servers), WORKER_PORT=18213
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18213
make corpus-import FILE=<scratch>/rules.yaml; make corpus-list    # see Notes: the corpus CLI ignores WORKER_PORT
python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml
python corpus_cli_on_port.py 18213 corpus list
make case-new; make case-paste CASE=case_3f9889c31823f1b7 FILE=<scratch>/era.835
make case-process CASE=case_3f9889c31823f1b7; make case-diagnose CASE=case_3f9889c31823f1b7
make case-show CASE=case_3f9889c31823f1b7
# control file: explanation role unavailable
make case-diagnose CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
# control file: both roles back
make case-diagnose CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
make case-new; make case-paste CASE=case_7175817abb8089b5 FILE=<scratch>/other_payer.835   # payer ZENITH MUTUAL
make case-process CASE=case_7175817abb8089b5; make case-diagnose CASE=case_7175817abb8089b5
make case-show CASE=case_7175817abb8089b5
```

```text
tests/test_us_6_2_explanation.py ...........................             [100%]
- generated xml file: .../evidence/US-6.2/junit.xml -
===================== 27 passed, 1056 deselected in 2.89s ======================

test_us_6_2_explanation.py::test_us_6_2_explanation_and_root_cause_shown PASSED
test_us_6_2_explanation.py::test_us_6_2_checklist_lists_missing_docs PASSED
test_us_6_2_explanation.py::test_us_6_2_items_off_the_card_dropped PASSED
test_us_6_2_explanation.py::test_us_6_2_no_valid_item_lists_every_document[...] PASSED (4 cases)
test_us_6_2_explanation.py::test_us_6_2_long_text_is_clipped_not_refused PASSED
test_us_6_2_explanation.py::test_us_6_2_checklist_from_item_numbers PASSED
test_us_6_2_explanation.py::test_us_6_2_no_rule_card_for_payer PASSED
test_us_6_2_explanation.py::test_us_6_2_unreadable_payer_matches_no_card PASSED
test_us_6_2_explanation.py::test_us_6_2_payer_cards_match_by_whole_words PASSED
test_us_6_2_explanation.py::test_us_6_2_two_spellings_are_one_payer PASSED
test_us_6_2_explanation.py::test_us_6_2_two_spellings_in_one_bundle_refused PASSED
test_us_6_2_explanation.py::test_us_6_2_required_documents_count_toward_the_size_cap PASSED
test_us_6_2_explanation.py::test_us_6_2_required_documents_round_trip PASSED
test_us_6_2_explanation.py::test_us_6_2_list_on_another_topic_refused PASSED
test_us_6_2_explanation.py::test_us_6_2_prompt_carries_cards_and_numbered_documents PASSED
test_us_6_2_explanation.py::test_us_6_2_unusable_explanations_are_refused[...] PASSED (4 cases)
test_us_6_2_explanation.py::test_us_6_2_progress_relayed PASSED
test_us_6_2_explanation.py::test_us_6_2_missing_explanation_model_keeps_classification PASSED
test_us_6_2_explanation.py::test_us_6_2_bad_explanation_reply_keeps_classification PASSED
test_us_6_2_explanation.py::test_us_6_2_stale_card_is_flagged PASSED
test_us_6_2_explanation.py::test_us_6_2_corpus_list_shows_required_documents PASSED

junit-node.xml: 3 US-6.2 cases, fail 0
  ✔ test_us_6_2_pane_explanation_and_root_cause_shown (0.324083ms)
  ✔ test_us_6_2_pane_checklist_lists_missing_docs (0.207542ms)
  ✔ test_us_6_2_pane_says_no_rule_card (0.1555ms)
case_diagnosis.test.mjs (whole file): ℹ tests 28  ℹ pass 28  ℹ fail 0

$ uv run pytest -m models -k "us_6" -rs --no-cov -p no:cacheprovider
SKIPPED [1] tests/test_us_6_1_diagnosis.py:772: Qwen3-8B weights not found at /Users/josoroma/Models/Qwen3-8B-4bit
SKIPPED [1] tests/test_us_6_2_explanation.py:594: Qwen3-14B weights not found at /Users/josoroma/Models/Qwen3-14B-4bit
SKIPPED [1] tests/test_us_6_2_explanation.py:637: classification weights not found at /Users/josoroma/Models/Qwen3-8B-4bit
===================== 3 skipped, 1080 deselected in 2.42s ======================

$ make corpus-import FILE=<scratch>/rules.yaml
error: worker_unavailable
make: *** [corpus-import] Error 1
$ make corpus-list
error: worker_unavailable
make: *** [corpus-list] Error 1
$ python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml
imported 3 code, 2 rule_card (5 chunks)
$ python corpus_cli_on_port.py 18213 corpus list
KIND             KEY                              VERIFIED         SOURCE
code             CARC/197                         2026-09-01       Synthetic code list
code             GROUP/CO                         2026-09-01       Synthetic code list
code             RARC/N286                        2026-09-01       Synthetic code list
rule_card        ACME Health/appeal_levels        2026-09-15       ACME Health provider manual (synthetic), section 9.0 (appeal limit 180 days)
rule_card        ACME Health/required_docs        2026-09-15       ACME Health provider manual (synthetic), section 9.1 (4 required documents)
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7
  "explanation": {
   "explanation": "The payer refused the visit because no authorization was on file for it. Ask the payer whether a retroactive authorization is possible, then appeal with the records.",
   "root_cause": "The authorization was not requested before the visit."
  },
  "checklist": [
   {"document": "Copy of the denial notice or remittance", "why": "The appeal must cite the denial."},
   {"document": "Medical records for the date of service", "why": "Shows the visit was medically necessary."}
  ],
  "rule_cards": [
   {"key": "ACME Health/appeal_levels", "payer": "ACME Health", "topic": "appeal_levels",
    "source": "ACME Health provider manual (synthetic), section 9.0", "verified_on": "2026-09-15", "stale": false},
   {"key": "ACME Health/required_docs", "payer": "ACME Health", "topic": "required_docs",
    "source": "ACME Health provider manual (synthetic), section 9.1", "verified_on": "2026-09-15", "stale": false}
  ]
# explanation role unavailable
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
failed        50%  model_unavailable
make: *** [case-diagnose] Error 1
$ make case-show CASE=case_3f9889c31823f1b7
diagnosis: prior_authorization high diagnosed_at 2026-10-31T18:28:20.582564Z, no explanation, 0 checklist items,
           rule_cards ['ACME Health/appeal_levels', 'ACME Health/required_docs']
# both roles back
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7
diagnosis: prior_authorization high diagnosed_at 2026-10-31T18:28:22.990729Z, explanation, 2 checklist items
$ make case-show CASE=case_7175817abb8089b5          (835 payer ZENITH MUTUAL)
payer: ZENITH MUTUAL
diagnosis: {'reason': 'prior_authorization', 'checklist': [], 'rule_cards': [], 'explanation?': True}
deadline: {"status": "no_rule_card", "due": null, "denial_date": "2026-10-15", "limit_days": null, "rule_card": null}

# worker log: "diagnose job failed: ModelUnavailableError" (type only, no case content)
# plaintext search of the scratch store: "The authorization was not requested": 0  "Payers often accept": 0
#   ("Medical records" and "authorization" appear only in the global corpus, as rule-card text)
```

Artifacts: `evidence/US-6.2/junit.xml`, `evidence/US-6.2/junit-node.xml`

## Failures

None.

## Notes

- The real model in rows 1 and 2: `test_us_6_2_explanation_real_model` and
  `test_us_6_2_diagnosis_real_models` are marked `models` and were SKIPPED because
  `~/Models/Qwen3-14B-4bit` and `~/Models/Qwen3-8B-4bit` are absent. No model was downloaded. That
  means the following are UNVERIFIED: whether Qwen3-14B's explanation is in fact plain language,
  whether its root cause is the likely one, and which card items it would choose. The
  explanation, root cause, and `why` texts checked above are canned replies from a fake
  OpenAI-compatible server. What the offline run does exercise: the real `explanation` prompt
  (its data blocks and the numbered card list), real reply parsing, a checklist built from item
  numbers only, card matching, storage, and the relay.
- What "missing" means: design decision 3 in
  `openspec/changes/us-6-2-explanation-checklist/design.md` defines a missing document as one
  "not in the case". The case holds only the denial documents, so every required document the
  appeal needs counts as missing. The prompt asks the model for "only the documents this appeal
  needs", and it does not list the case's attached documents. I observed that every checklist item
  comes from the card. Whether an item is truly absent is not checked against the case's
  attachments, and the design defers tracking what was gathered to a later pane story.
- The pane: the node tests render the pane under `register-fakes.mjs`. The pane was not seen in a
  live Hermes desktop. `junit-node.xml` holds only the `test_us_6_2_*` tests. The other US-6.2
  pane tests, "a diagnosis whose explanation did not run shows no explanation or checklist",
  "cards without required documents say so; malformed entries are dropped", "an unreadable payer
  asks the biller to confirm it, not the manager to add a card", and "a card that became stale
  after the diagnosis is flagged today", passed in the whole-file run (28/28).
- The spec-delta scenarios (`openspec/changes/us-6-2-explanation-checklist/specs/`) were exercised
  as follows:
  - "The explanation model is missing": `test_us_6_2_missing_explanation_model_keeps_classification`
    (`classifying`, then `explaining`, then `failed`/`model_unavailable`; the classification and
    the rule cards stay; the explanation is null and the checklist empty). The operator run showed
    the same.
  - "The model names a document that is not on the card": `test_us_6_2_items_off_the_card_dropped`.
  - "No rule card for the payer": `test_us_6_2_no_rule_card_for_payer` (the prompt says "No rule
    card is on file for this payer."), `test_us_6_2_unreadable_payer_matches_no_card`, and
    `test_us_6_2_pane_says_no_rule_card` (a `note` that begins "No rule card is on file for this
    payer"). In the operator run, case `case_7175817abb8089b5` (payer ZENITH MUTUAL) got an
    explanation, `checklist: []`, and `rule_cards: []`.
  - "A payer named inside another payer's name": `test_us_6_2_payer_cards_match_by_whole_words`
    (`AETNA MEDICARE ADVANTAGE` and `AMBETTER FROM HEALTH NET` match no card).
  - "Two spellings of one payer": `test_us_6_2_two_spellings_are_one_payer` and
    `test_us_6_2_two_spellings_in_one_bundle_refused`.
  - corpus-import, "Required documents are stored with the card": `test_us_6_2_required_documents_round_trip`.
    "A list on another topic is refused": `test_us_6_2_list_on_another_topic_refused`.
  - Also: `test_us_6_2_bad_explanation_reply_keeps_classification` (`diagnosis_failed`, the
    classification stays).
- How the operator run was isolated: it is the same scratch run as US-6.1. The real `create_app`
  ran with a scratch `HERMES_HOME` and `MODELS_HOME`, an `InMemoryKeyProvider`, and fake
  embedding, classification, and explanation servers, on 127.0.0.1:18213. All data was synthetic.
  The worker was stopped afterwards, and the real `~/.hermes` was not touched.
- Something I noticed, outside this story's criteria: `make corpus-import` and `make corpus-list`
  (the runbook's way to load and check the `required_docs` card) do not follow `WORKER_PORT`.
  `claimcoach.cli._client()` always targets `WorkerConfig().port` (18200), so against the scratch
  worker on 18213 both printed `error: worker_unavailable`. `corpus_cli_on_port.py` ran the same
  CLI `build_parser()` and `run()` with only the client's base URL changed. With the default
  port, the worker and the corpus targets agree.
