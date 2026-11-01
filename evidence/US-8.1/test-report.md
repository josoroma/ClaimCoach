# Test Report: US-8.1 Record a Case Outcome

Change: us-8-1-case-outcome
Story: US-8.1
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; sqlite3 CLI (read-only) as an independent reader of the store

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Outcome is recorded on the case: Then the case stores that outcome and the case is closed" | PASS | `test_us_8_1_outcome_recorded[overturned]`, `[upheld]`, and `[written_off]` go through the gateway. Each starts from an open case (`closed_at` is null). The case that comes back has `outcome.outcome` equal to the value posted and `closed_at` equal to `outcome.recorded_at`. The store's `outcome(case_id)` and `case_record(...).closed_at` agree with it. The last two audit entries are `outcome_recorded` then `case_closed`, and a later paste is refused with `409 case_closed`. Also passing: `test_us_8_1_case_shows_its_outcome`, `test_us_8_1_outcome_and_close_are_one_transaction`, and `test_us_8_1_outcome_through_the_worker` (the `WorkerClient` with profile `biller-b`). Pane (node): `test_us_8_1_pane_outcome_recorded` (Mark only names the choice, Cancel drops it, **Close the case** posts it). In the same file, "a closed case keeps only Refresh, New case, the exports, and the outcome" passes too. Operator: on scratch case `case_6effbbb35d0a971f`, which was open with one pasted document, `make case-outcome OUTCOME=overturned` returned `outcome: overturned` and `closed_at` equal to `recorded_at` (`2026-10-31T21:44:28.806360Z`). On two fresh cases, `upheld` and `written_off` returned the same: closed, with `closed_at == recorded_at`. Afterwards `make case-paste` answered `409 case_closed` and `make case-process` answered `error: case_closed`. The audit has `outcome_recorded` (seq 6), then `case_closed` (seq 7). `sqlite3 -readonly` shows the `outcomes` table (`case_id`, `outcome`, `recorded_at`, `features`) holding the three rows. It is a separate table from `documents` and has no document text |

## Evidence Commands

```bash
make evidence STORY=US-8.1
make test-story STORY=US-8.1
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/case_outcome.test.mjs
uv run pytest -m "not models" -p no:cacheprovider --no-cov \
  -k "test_us_7_3_no_transmitting_route or test_us_1_5_runbooks_have_sections or test_us_4_5" -q
# operator run against a scratch worker (serve_outcome_worker.py in the session scratchpad:
# real create_app, tests/fakes make_service with a FakeModelServer and InMemoryKeyProvider, a
# per-launch token from issue_token, and a stand-in extraction runner that holds the job until a
# release file exists); synthetic data only
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18211
make case-new; make case-paste CASE=case_6effbbb35d0a971f FILE=<scratch>/letter.txt
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=won
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=up%
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=Overturned
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME="upheld upheld"
make case-outcome CASE=case_6effbbb35d0a971f                      # no OUTCOME
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME='upheld","note":"x'
curl ... -X POST "http://127.0.0.1:18211/cases/<id>/outcome?profile=default" -d '<body>'  # bodies the make guard never sends
make case-process CASE=case_6effbbb35d0a971f &                    # held job
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=overturned   # while it runs
touch <scratch>/release                                           # job ends
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=overturned
make case-outcome CASE=case_6effbbb35d0a971f OUTCOME=written_off  # correction
make case-show CASE=case_6effbbb35d0a971f
make case-paste CASE=case_6effbbb35d0a971f FILE=<scratch>/letter.txt
make case-process CASE=case_6effbbb35d0a971f
make case-new; make case-outcome CASE=<new> OUTCOME=upheld        # and again with written_off
make corpus-audit CASE=case_6effbbb35d0a971f
curl ... "http://127.0.0.1:18211/corpus/audit?profile=default&case_id=case_6effbbb35d0a971f"
sqlite3 -readonly "file:<scratch>/hermes/plugin-data/claimcoach/user/corpus.sqlite3?mode=ro" \
  ".tables" "pragma table_info(outcomes)" "select case_id, outcome, recorded_at, features from outcomes"
kill -TERM <worker pid>; lsof -nP -iTCP:18211 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-8.1
tests/test_us_8_1_case_outcome.py ...................                    [100%]
- generated xml file: .../evidence/US-8.1/junit.xml -
===================== 19 passed, 1294 deselected in 1.80s ======================
junit.xml: tests=19 failures=0 errors=0
  test_us_8_1_outcome_recorded[overturned|upheld|written_off]
  test_us_8_1_case_shows_its_outcome
  test_us_8_1_outcome_and_close_are_one_transaction
  test_us_8_1_a_later_outcome_corrects_the_first
  test_us_8_1_a_purged_case_takes_a_correction
  test_us_8_1_outcome_refused_while_a_job_runs
  test_us_8_1_outcome_waits_for_a_real_job
  test_us_8_1_a_job_on_a_case_closed_meanwhile_holds_no_model[Extractor|Diagnoser]
  test_us_8_1_invalid_outcomes[body0..body4, upheld]   (6 bodies)
  test_us_8_1_outcome_refusals
  test_us_8_1_outcome_through_the_worker
junit-node.xml: 3 US-8.1 cases, fail 0
  test_us_8_1_pane_outcome_recorded
  test_us_8_1_pane_outcome_corrected
  test_us_8_1_pane_outcome_refused_while_a_job_runs

$ make test-story STORY=US-8.1
===================== 19 passed, 1294 deselected in 1.70s ======================
ℹ tests 11  ℹ pass 11  ℹ fail 0      (3 US-8.1 tests, the other files filtered out)
case_outcome.test.mjs (whole file): ℹ tests 8  ℹ pass 8  ℹ fail 0
test_us_7_3_no_transmitting_route, test_us_1_5_runbooks_have_sections, test_us_4_5*: 34 passed

$ make case-outcome ... OUTCOME=won        (likewise up%, Overturned, "upheld upheld", none, 'upheld","note":"x')
Makefile:459: *** usage: make case-outcome CASE=<case id> OUTCOME=<overturned|upheld|written_off>.  Stop.
exit=2                                      (each of the six; nothing reached the worker)
$ make case-show (after the refusals)
outcome None closed_at None

curl, straight to the worker:
{"outcome":"won"} | {"outcome":"up%"} | {"outcome":"Overturned"} | {"outcome":"upheld","note":"Called Jane Doe"} | {} | "upheld"
{"ok":false,"error":{"code":"invalid_request","message":"The request did not match the expected parameters."}} HTTP 422   (all six; no "Jane" echoed)
unknown case_0000000000000000 -> {"ok":false,"error":{"code":"case_not_found","message":"No such case in this profile."}} HTTP 404
bad id "bad id!"              -> invalid_request HTTP 422

$ make case-process ... &          -> extracting    10%   (held)
$ make case-outcome ... OUTCOME=overturned
curl: (22) The requested URL returned error: 409
    "error": {"code": "model_busy", "message": "The local model is busy; try again when the current work finishes."}
make: *** [case-outcome] Error 22
after busy refusal: outcome None closed_at None
(release) -> done         100%   process exit=0

$ make case-outcome ... OUTCOME=overturned
 "opened_at": "2026-10-31T21:43:51.293698Z",
 "closed_at": "2026-10-31T21:44:28.806360Z",
 "outcome": {"case_id": "case_6effbbb35d0a971f", "outcome": "overturned", "recorded_at": "2026-10-31T21:44:28.806360Z"}
$ make case-outcome ... OUTCOME=written_off   (correction)
 "closed_at": "2026-10-31T21:44:28.806360Z",
 "outcome": {"case_id": "case_6effbbb35d0a971f", "outcome": "written_off", "recorded_at": "2026-10-31T21:44:30.229592Z"}
$ make case-show ...
{"closed_at": "2026-10-31T21:44:28.806360Z", "outcome": {..., "outcome": "written_off", "recorded_at": "2026-10-31T21:44:30.229592Z"}}
$ make case-paste ...  (closed)   -> 409 "code": "case_closed"  "This case is closed, so it takes no new documents or changes."
$ make case-process ... (closed)  -> error: case_closed
case_8f90a7862806c039 upheld:      closed_at 2026-10-31T21:44:41.734865Z == recorded_at True
case_c2eefa000e918297 written_off: closed_at 2026-10-31T21:44:42.059050Z == recorded_at True

$ make corpus-audit CASE=case_6effbbb35d0a971f
error: worker_unavailable          (expected against this harness; see Notes)
GET /corpus/audit (case_6effbbb35d0a971f):
  seq 1 case_created | 2 document_added | 3-5 case_opened | 6 outcome_recorded 21:44:28.806470Z
  seq 7 case_closed 21:44:28.806498Z | 8 outcome_recorded 21:44:30.229681Z | 9 case_opened
  entries are {seq, at, action, case_id, profile} only; no entry for the busy or invalid requests

$ sqlite3 -readonly ... corpus.sqlite3
audit_log    case_items    cases    chunks    documents    meta    outcomes
outcomes columns: case_id TEXT pk | outcome TEXT | recorded_at TEXT | features TEXT
case_6effbbb35d0a971f|written_off|2026-10-31T21:44:30.229592+00:00|
case_8f90a7862806c039|upheld|2026-10-31T21:44:41.734865+00:00|
case_c2eefa000e918297|written_off|2026-10-31T21:44:42.059050+00:00|
plaintext search of the scratch store for "SYNTH-8-1", "SYN-0001", "Jane Doe": 0 files
after SIGTERM: port 18211 free; no harness process left
```

Artifacts: `evidence/US-8.1/junit.xml`, `evidence/US-8.1/junit-node.xml`

## Failures

None.

## Notes

- Spec-delta scenarios (`openspec/changes/us-8-1-case-outcome/specs/case-outcome/spec.md`):
  - "Outcome is recorded on the case": WHEN the biller marks an open case's outcome as
    overturned, upheld, or written off, THEN the case stores that outcome and the case is closed.
    PASS, the same evidence as row 1.
  - "A later outcome corrects the first": WHEN the biller marks a closed case's outcome again,
    THEN the stored outcome is replaced AND the case keeps the close date the first outcome gave
    it. PASS. `test_us_8_1_a_later_outcome_corrects_the_first` checks the new outcome, the same
    `closed_at`, 2 `outcome_recorded`, and 1 `case_closed`.
    `test_us_8_1_a_purged_case_takes_a_correction` checks that a purged case also takes a
    correction. Pane: `test_us_8_1_pane_outcome_corrected`. Operator: `overturned` was corrected
    to `written_off`. The outcome and `recorded_at` were replaced, and `closed_at` stayed at
    `21:44:28.806360Z`. The audit has a second `outcome_recorded` and no second `case_closed`.
    The purged-case correction was exercised only by the test, not in the operator run.
  - "An outcome while a job runs": WHEN the biller marks the outcome of a case whose extraction,
    diagnosis, or draft is running, THEN the request is refused with model_busy and nothing is
    stored. PASS. These tests cover it: `test_us_8_1_outcome_refused_while_a_job_runs` (any
    running job), `test_us_8_1_outcome_waits_for_a_real_job` (the real `JobRegistry`: refused,
    then recorded once the job ends), `test_us_8_1_a_job_on_a_case_closed_meanwhile_holds_no_model`
    (Extractor and Diagnoser), and the pane's `test_us_8_1_pane_outcome_refused_while_a_job_runs`.
    Operator: `make case-outcome` during a held extraction answered `409 model_busy`. Afterwards
    `outcome` was null, `closed_at` was null, and the audit had no `outcome_recorded`. The
    operator run used only an extraction job. The job was a stand-in runner, not the real
    Extractor, because the harness has no extraction model. Diagnosis and draft jobs are covered
    only by the tests. Draft jobs go through the same `JobRegistry.running` check.
  - "An invalid outcome": WHEN the outcome is not one of the three values or the body has another
    key, THEN the request is refused with invalid_request and nothing is stored. PASS.
    `test_us_8_1_invalid_outcomes` covers six bodies, including an extra `note` key holding a
    name, which is not echoed. `test_us_8_1_outcome_refusals` covers `case_not_found`, a bad ID,
    and a `text/plain` body. Operator: `make` refused `won`, `up%`, `Overturned`, two words, a
    missing value, and a JSON-injection attempt before calling the worker (exit 2), and the case
    stayed open with no outcome. The same bad bodies sent to the worker with curl answered
    `422 invalid_request`.
- The pane: the node tests render the pane under `register-fakes.mjs`. The confirmation dialog
  ("Close the case" / "Cancel") and the disabled editing controls of a closed case were not seen
  in a live Hermes desktop. That remains UNVERIFIED in a live app; it is beyond what
  `case_outcome.test.mjs` exercises.
- How the operator run was isolated: `serve_outcome_worker.py` in this tester's scratchpad
  (`.../scratchpad/tester-8-1/`), not in the repo. It ran the real `create_app` with
  `HERMES_HOME` and `MODELS_HOME` set to scratch folders (the script refuses any other path), an
  `InMemoryKeyProvider` (no Keychain item), and an in-process `FakeModelServer` for the corpus
  embedder and reranker. It served on 127.0.0.1:18211 with `WORKER_PORT=18211`. All data was
  synthetic. The worker was stopped with SIGTERM, and port 18211 was free afterwards. No model
  was downloaded, and the real `~/.hermes` and any real worker were not touched.
- `make corpus-audit` (runbook step 2) printed `error: worker_unavailable` against this harness.
  This is expected, as in US-7.1: since 13b88f3 the corpus CLI sends the token only to a worker
  that the launcher recorded in its PID file, and this harness was not started by the launcher.
  I read the same audit through `GET /corpus/audit` with curl and the scratch token instead.
- The harness's worker log was empty because the script does not call `configure_logging`. So
  the operator run does not show what a real worker logs for an outcome. The store search found
  no plaintext copy of the synthetic text.
- The runbook says a correction "keeps the first `closed_at`", and that `closed_at` equals the
  first outcome's `recorded_at`. Both matched to the microsecond. A refusal from the worker shows
  `make: *** [case-outcome] Error 22` (curl's code). A refusal by the `make` guard shows the usage
  line. Both give `make` exit status 2.
