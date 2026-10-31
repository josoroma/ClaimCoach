# Test Report: US-6.3 Appeal Deadline

Change: us-6-3-appeal-deadline
Story: US-6.3
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; Qwen3-8B-4bit and Qwen3-14B-4bit weights absent

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Deadline is computed from the rule card: Then the case shows the deadline equal to the denial date plus the rule card's limit" | PASS | `test_us_6_3_deadline_from_rule_card`: an `ACME Health` `appeal_levels` card has `appeal_limit_days` 180. The extracted 835 case has `denial_date` 2026-10-15. After the case is diagnosed, its deadline is `AppealDeadline(status="computed", due=2026-10-15 + 180 days, denial_date=2026-10-15, limit_days=180, rule_card="ACME Health/appeal_levels")`, and `due == 2027-04-13`. `test_us_6_3_compute_deadline_is_pure[...]` (4 cases, among them 2026-10-15 + 180 = 2027-04-13, 2026-10-15 + 1 = 2026-10-16, 2027-12-31 + 60 = 2028-02-29 across a leap day, and 2026-01-31 + 30 = 2026-03-02); the function's and the module's docstrings cite US-6.3. `test_us_6_3_compute_deadline_refuses_no_limit` (typed `(date, int) -> date`). `test_us_6_3_deadline_model_is_strict`: a computed deadline must name its date, limit, and card and equal its denial date plus its limit, and an unknown one has no due date. `test_us_6_3_835_gives_the_denial_date` (DTM*405, then GS04, then BPR16), `test_us_6_3_835_dates_come_from_the_first_claims_transaction`, `test_us_6_3_appeal_limit_round_trip`. Pane (node): `test_us_6_3_pane_deadline_from_rule_card` renders "Appeal by 2027-04-13: 180 days from the denial date 2026-10-15 (ACME Health/appeal_levels rule card)." with `data-passed` false, and shows it with no diagnosis. Operator: with the synthetic card (180 days) imported, `make case-show` printed `"deadline": {"status": "computed", "due": "2027-04-13", "denial_date": "2026-10-15", "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}` after `make case-process`, and the same after `make case-diagnose`. `make case-confirm FIELD=denial_date VALUE=2026-10-20` changed it to `due` `2027-04-18`. A re-imported card with 90 days changed the next `make case-show` to `due` `2027-01-18` without a new diagnosis |

## Evidence Commands

```bash
make evidence STORY=US-6.3
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_6_1 or us_6_2 or us_6_3" -v
uv run pytest -m models -k "us_6" -rs --no-cov -p no:cacheprovider
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_6_ plugin/desktop/tests/
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/case_diagnosis.test.mjs
# operator run against a scratch worker (serve_case_worker.py: real create_app, InMemoryKeyProvider,
# fake embedding, classification, and explanation servers), WORKER_PORT=18213
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18213
python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml   # make corpus-import ignores WORKER_PORT (Notes)
make case-new; make case-paste CASE=case_3f9889c31823f1b7 FILE=<scratch>/era.835
make case-process CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
make case-diagnose CASE=case_3f9889c31823f1b7; make case-show CASE=case_3f9889c31823f1b7
make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=1760486400
make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=15/10/2026
make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=2026-10-20
make case-show CASE=case_3f9889c31823f1b7
python corpus_cli_on_port.py 18213 corpus import <scratch>/rules-90.yaml   # ACME Health appeal_levels, 90 days
make case-show CASE=case_3f9889c31823f1b7
make case-new; make case-paste CASE=case_7175817abb8089b5 FILE=<scratch>/other_payer.835   # payer ZENITH MUTUAL
make case-process CASE=case_7175817abb8089b5; make case-diagnose CASE=case_7175817abb8089b5; make case-show CASE=case_7175817abb8089b5
make case-new; make case-paste CASE=case_e90293f6f05a0ee1 FILE=<scratch>/undated.835       # no DTM*405, GS04, or BPR16 date
make case-process CASE=case_e90293f6f05a0ee1; make case-show CASE=case_e90293f6f05a0ee1
make case-diagnose CASE=case_e90293f6f05a0ee1; make case-show CASE=case_e90293f6f05a0ee1
make case-confirm CASE=case_e90293f6f05a0ee1 FIELD=denial_date VALUE=2026-08-31
make case-confirm CASE=case_e90293f6f05a0ee1 FIELD=denial_date VALUE=2026-10-20
```

```text
tests/test_us_6_3_deadline.py .........................                  [100%]
- generated xml file: .../evidence/US-6.3/junit.xml -
===================== 25 passed, 1058 deselected in 2.52s ======================

test_us_6_3_deadline.py::test_us_6_3_deadline_from_rule_card PASSED
test_us_6_3_deadline.py::test_us_6_3_compute_deadline_is_pure[...] PASSED (4 cases)
test_us_6_3_deadline.py::test_us_6_3_compute_deadline_refuses_no_limit PASSED
test_us_6_3_deadline.py::test_us_6_3_unknown_deadline_says_why PASSED
test_us_6_3_deadline.py::test_us_6_3_implausible_denial_date_is_not_used[...] PASSED (6 cases)
test_us_6_3_deadline.py::test_us_6_3_deadline_model_is_strict PASSED
test_us_6_3_deadline.py::test_us_6_3_no_rule_card PASSED
test_us_6_3_deadline.py::test_us_6_3_deadline_follows_the_case_without_a_model PASSED
test_us_6_3_deadline.py::test_us_6_3_two_spellings_use_the_freshest_limit PASSED
test_us_6_3_deadline.py::test_us_6_3_unreadable_denial_date PASSED
test_us_6_3_deadline.py::test_us_6_3_835_gives_the_denial_date PASSED
test_us_6_3_deadline.py::test_us_6_3_835_dates_come_from_the_first_claims_transaction PASSED
test_us_6_3_deadline.py::test_us_6_3_extraction_prompt_asks_for_the_denial_date PASSED
test_us_6_3_deadline.py::test_us_6_3_older_extraction_loads PASSED
test_us_6_3_deadline.py::test_us_6_3_denial_date_confirmable PASSED
test_us_6_3_deadline.py::test_us_6_3_appeal_limit_round_trip PASSED
test_us_6_3_deadline.py::test_us_6_3_limit_on_another_topic_refused PASSED

junit-node.xml: 3 US-6.3 cases, fail 0
  ✔ test_us_6_3_pane_deadline_from_rule_card (0.213ms)
  ✔ test_us_6_3_pane_flags_passed_deadline (0.128542ms)
  ✔ test_us_6_3_pane_unknown_deadline_says_why (0.191709ms)
case_diagnosis.test.mjs (whole file): ℹ tests 28  ℹ pass 28  ℹ fail 0

$ python corpus_cli_on_port.py 18213 corpus import <scratch>/rules.yaml
imported 3 code, 2 rule_card (5 chunks)
rule_card  ACME Health/appeal_levels  2026-09-15  ACME Health provider manual (synthetic), section 9.0 (appeal limit 180 days)
$ make case-process CASE=case_3f9889c31823f1b7
extracting     0%
extracting    95%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7          (extracted, not diagnosed)
denial_date: {'value': '2026-10-15', 'status': 'extracted'}
payer_name: {'value': 'ACME HEALTH PLAN', 'status': 'extracted'}
diagnosis: None
deadline: {"status": "computed", "due": "2027-04-13", "denial_date": "2026-10-15", "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}
$ make case-diagnose CASE=case_3f9889c31823f1b7
classifying    0%
explaining    50%
done         100%
$ make case-show CASE=case_3f9889c31823f1b7          (diagnosed)
 "deadline": {"status": "computed", "due": "2027-04-13", "denial_date": "2026-10-15", "limit_days": 180,
              "rule_card": "ACME Health/appeal_levels"}
$ make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=1760486400
curl: (22) The requested URL returned error: 422
    "error": { "code": "invalid_request", "message": "The request did not match the expected parameters." }
make: *** [case-confirm] Error 22
$ make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=15/10/2026
curl: (22) The requested URL returned error: 422
        "code": "invalid_request",
$ make case-confirm CASE=case_3f9889c31823f1b7 FIELD=denial_date VALUE=2026-10-20
denial_date: {'value': '2026-10-20', 'status': 'confirmed'}  diagnosis_stale: True
deadline: {"status": "computed", "due": "2027-04-18", "denial_date": "2026-10-20", "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}
$ python corpus_cli_on_port.py 18213 corpus import <scratch>/rules-90.yaml
imported 1 rule_card (1 chunks)
rule_card  ACME Health/appeal_levels  2026-10-30  ACME Health provider manual (synthetic), section 9.0 rev 2 (appeal limit 90 days)
$ make case-show CASE=case_3f9889c31823f1b7          (after the re-import, no diagnosis run)
deadline: {"status": "computed", "due": "2027-01-18", "denial_date": "2026-10-20", "limit_days": 90, "rule_card": "ACME Health/appeal_levels"}
$ make case-show CASE=case_7175817abb8089b5          (payer ZENITH MUTUAL, diagnosed)
deadline: {"status": "no_rule_card", "due": null, "denial_date": "2026-10-15", "limit_days": null, "rule_card": null}
$ make case-show CASE=case_e90293f6f05a0ee1          (835 without a denial date)
denial_date: {'value': None, 'status': 'unreadable'} | needs_confirmation: ['denial_date']
deadline: {"status": "no_denial_date", "due": null, "denial_date": null, "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}
$ make case-diagnose CASE=case_e90293f6f05a0ee1  ->  classifying 0%, explaining 50%, done 100%
$ make case-show CASE=case_e90293f6f05a0ee1          (diagnosed: deadline unchanged, no_denial_date)
$ make case-confirm CASE=case_e90293f6f05a0ee1 FIELD=denial_date VALUE=2026-08-31      (before the 2026-09-01 service)
denial_date: {'value': '2026-08-31', 'status': 'confirmed'}
deadline: {"status": "implausible_denial_date", "due": null, "denial_date": "2026-08-31", "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}
$ make case-confirm CASE=case_e90293f6f05a0ee1 FIELD=denial_date VALUE=2026-10-20
deadline: {"status": "computed", "due": "2027-04-18", "denial_date": "2026-10-20", "limit_days": 180, "rule_card": "ACME Health/appeal_levels"}
```

Artifacts: `evidence/US-6.3/junit.xml`, `evidence/US-6.3/junit-node.xml`

## Failures

None.

## Notes

- No model computes the deadline. `compute_deadline` is a pure date addition, and the denial date
  in every run here came from the 835 parser (no model) or from a biller confirmation. A denial
  date read from an EOB or a letter by the extraction model (Qwen3-VL-8B, US-5.2) was not
  exercised. `test_us_6_3_extraction_prompt_asks_for_the_denial_date` only checks that the
  extraction prompt asks for it, so how well the real vision model reads a notice date is
  UNVERIFIED. The `models` run for `us_6` skipped all three of its tests (Qwen3-8B-4bit and
  Qwen3-14B-4bit absent). None of them is a deadline test.
- The Gherkin says "When diagnosis runs". The deadline is in fact computed on every read of an
  extracted case, before and after diagnosis (spec delta: "Whenever a case with an extraction is
  read"). The operator run showed the same deadline before and after `make case-diagnose`, and it
  showed a deadline on cases whose diagnosis had failed. I read this as a superset of the
  scenario, not a deviation.
- The pane: `test_us_6_3_pane_deadline_from_rule_card` and the other pane tests run under
  `register-fakes.mjs`. The deadline line was not seen in a live Hermes desktop. "The denial date
  is a field the biller confirms", "isoToday reads this Mac's calendar date", and "malformed
  deadlines are dropped" passed in the whole-file run (28/28).
- The spec-delta scenarios (`openspec/changes/us-6-3-appeal-deadline/specs/`) were exercised as
  follows:
  - "A confirmed date or a new card shows at once": `test_us_6_3_deadline_follows_the_case_without_a_model`
    (a card added after extraction, a failed classification, and a card re-imported with 90 days)
    and `test_us_6_3_unreadable_denial_date`. Operator: the deadline was due 2027-04-18 after the
    confirmation and 2027-01-18 after the 90-day re-import, with no new diagnosis.
  - "The deadline has passed": `test_us_6_3_pane_flags_passed_deadline`. The due date itself is
    still in time. The next day gives `data-passed` true, "This deadline has passed.", and red
    bold text. The API carries no "passed" flag (the pane judges it with the Mac's date), so the
    operator run could not show this.
  - "No rule card for the payer": `test_us_6_3_no_rule_card`. In the operator run, case
    `case_7175817abb8089b5` (ZENITH MUTUAL) got `no_rule_card` with no due date.
  - "The denial date is unreadable": `test_us_6_3_unreadable_denial_date`. In the operator run,
    case `case_e90293f6f05a0ee1` listed `denial_date` for confirmation and got `no_denial_date`
    with `limit_days` 180, both before and after diagnosis, until the confirmation.
  - "An implausible denial date": `test_us_6_3_implausible_denial_date_is_not_used[...]` (after
    today, a misread year, 9999-12-31, before the service date; and the day of service and today
    both compute). Operator: a confirmed 2026-08-31 gave `implausible_denial_date` with no due
    date.
  - Precedence of unknown reasons: `test_us_6_3_unknown_deadline_says_why` (`no_payer`, then
    `no_rule_card`, then `no_appeal_limit`, then `no_denial_date`) and
    `test_us_6_3_pane_unknown_deadline_says_why` (each status has its own sentence).
  - case-extraction, "The 835 gives the denial date": `test_us_6_3_835_gives_the_denial_date`.
    "A batch of 835 transactions": `test_us_6_3_835_dates_come_from_the_first_claims_transaction`.
    "An older extraction loads": `test_us_6_3_older_extraction_loads`. "A number is not a date":
    `test_us_6_3_denial_date_confirmable`, and in the operator run `VALUE=1760486400` and
    `VALUE=15/10/2026` each got 422 `invalid_request`.
  - corpus-import, "The appeal limit is stored with the card": `test_us_6_3_appeal_limit_round_trip`,
    and the operator corpus list showed "(appeal limit 180 days)". "A limit on another topic is
    refused": `test_us_6_3_limit_on_another_topic_refused` (0, 3651, 1.5, `True`, and `"180"`
    are refused as well).
- The SPECS open questions are resolved by the change's design. The clock counts from the
  payer's decision date (DTM*405, then GS04, then BPR16, or the notice date). A missing card or
  limit gives a named status, and no default limit is used. The test cards are built with the
  bundle model (`RuleCard` with `appeal_limit_days`), as US-4.3 defined it.
- How the operator run was isolated: it is the same scratch run as US-6.1 and US-6.2. The real
  `create_app` ran with a scratch `HERMES_HOME` and `MODELS_HOME`, an `InMemoryKeyProvider`, and
  fake model servers, on 127.0.0.1:18213. All data was synthetic. The worker was stopped
  afterwards, and the real `~/.hermes` was not touched.
- Something I noticed, outside this story's criterion: `make corpus-import` and `make corpus-list`
  do not follow `WORKER_PORT`. The corpus CLI always targets port 18200, so against the scratch
  worker on 18213 they printed `error: worker_unavailable`. The cards were imported through the
  same CLI `run()`, with only the client's base URL set to 18213 (`corpus_cli_on_port.py`).
