# Test Report: US-12.2 Classification and Draft-Quality Gates

Change: us-12-2-quality-gates
Story: US-12.2
Verdict: pass
Coverage: 7/9 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; no ClaimCoach worker running (`make worker-status`: `not running`); the user's `~/.hermes/plugin-data/claimcoach/models.yaml` fails validation (`python -m claimcoach.models check`)

## Acceptance Criteria Evaluated

Row 1 is the SPECS.md scenario, run against fake models. Rows 2 to 7 are the change spec's extra
scenarios and requirements. Rows 8 and 9 are the PRD measurements on real models and real manager
reviews, which were not run (see Notes). The code tested is the plugin as of 22:29 and the tests
as of 22:37.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Classification eval reports accuracy: Then it reports accuracy and exits non-zero if accuracy is below 85%" | PASS | `test_us_12_2_classification_eval_reports_accuracy` passes: metric `accuracy`, target 0.85, 15/20 = 0.75, a `by_category` entry for each of the 10 labels, exit != 0, `BLOCKED`. `test_us_12_2_cases_without_a_diagnosis_are_misses` passes: exit 1, `errors` = `denial_00x:diagnosis_failed`. Operator run: `make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good` against a scratch loopback worker over fake models printed `accuracy 0.7500 (15/20), target 0.85: BLOCKED`, ten per-reason lines, and five `missed denial_0xx:<reason>` lines, then `make: *** [eval-classification] Error 1`. (The fake vision model reads every EOB PDF as CO-197) |
| 2 | "Accuracy at target passes (change spec): THEN the eval exits 0 and the report says it passed" | PASS | `test_us_12_2_classification_passes_at_target` passes (14/14). Operator: `make eval-classification DENIAL_SET=<scratch>/nopdf.json` (the set's 14 non-PDF cases) printed `accuracy 1.0000 (14/14), target 0.85: PASS`, and the report has `passed: true`. `LIMIT=3` gave `1.0000 (3/3) ... PASS`. `LIMIT=0` was refused with `argument --limit: must be a whole number of 1 or more` |
| 3 | "Cases are purged (change spec): THEN none of them holds a document or a diagnosis" | PASS | These pass: `test_us_12_2_every_eval_case_is_purged`, `test_us_12_2_unpurgeable_cases_are_reported`, and `test_us_12_2_unexpected_failure_names_its_type_only`. After the "good" operator round (20 + 14 + 3 classification, 20 + 6 latency, 1 egress), `make case-list WORKER_PORT=18217` reported `64 cases; unpurged: 0; with documents: 0; diagnosed/drafted: 0` |
| 4 | "Seventy percent passes (change spec): WHEN 7 of 10 reviewed drafts were approved with minor edits THEN the eval exits 0" | PASS | `test_us_12_2_draft_acceptance_gate` (7/10 exits 0) passes. Operator: `make eval-drafts REVIEWS=<scratch>/reviews/pass-7-of-10.json EVAL_OUT=<scratch>/out2/pass-7-of-10` (tester-made synthetic letters; each minor edit replaces one sentence) printed `acceptance_rate 0.7000 (7/10), target 0.70: PASS`, per-reason lines, and `missed r07:coding_error`, `r08:timely_filing`, `r09:eligibility`. `make` exited 0, and the direct CLI exited 0 |
| 5 | "Below seventy percent blocks (change spec): WHEN 6 of 10 were THEN the eval exits non-zero" | PASS | `test_us_12_2_draft_acceptance_gate` (6/10 exits 1) passes. Operator: `block-6-of-10.json` printed `acceptance_rate 0.6000 (6/10), target 0.70: BLOCKED`, then `make: *** [eval-drafts] Error 1`, and the direct CLI exited 1. A review file with a misspelt key (`finall`) and a missing file each gave `not measured: eval set <path> is missing or not a valid eval set` (CLI exit 2) |
| 6 | "A cut draft is not a minor edit (change spec): WHEN the manager approved the draft with its last quarter removed THEN that draft is not accepted with minor edits" | PASS | `test_us_12_2_rubric_counts_cuts_and_additions` (cut gives 0.75; padded by 36% is below 0.85; one reworded passage gives 0.95) and `test_us_12_2_similarity_of_letters` pass. Operator: `cut-quarter.json` (one review whose `final` is the first 75% of the draft's words) printed `acceptance_rate 0.0000 (0/1), target 0.70: BLOCKED` and `missed r00:coding_error`, and the CLI exited 1 |
| 7 | "`make evals` SHALL count the eval as not measured, and the release as blocked, when no review file is given (change spec)" | PASS | `make -n evals` lists `eval-redaction eval-classification eval-drafts eval-latency eval-egress`. `make eval-drafts` without `REVIEWS` printed `not measured: make eval-drafts REVIEWS=<the manager's draft reviews (JSON)>` (exit 2). `make evals` with no worker and no `REVIEWS` ended `release blocked by: eval-redaction eval-classification eval-drafts eval-latency eval-egress` and `make: *** [evals] Error 1` |
| 8 | "Classification eval reports accuracy" on the real local models (`test_us_12_2_classification_on_real_models`, marked `models`) | UNVERIFIED | `uv run pytest -m models -k us_12_` reported `SKIPPED ... no ClaimCoach worker on port 18200`. With no worker, `make eval-classification` printed `not measured: the worker on port 18200 answered worker_unavailable` (exit 2). The PRD's 85% has not been measured |
| 9 | "drafts accepted with minor edits ≥ 70%" (PRD §4) on the billing manager's real review file | UNVERIFIED | No manager review file exists. The rubric was exercised only on tester-made synthetic letters (rows 4 to 6) |

## Evidence Commands

```bash
make test-story STORY=US-12.2
make evidence STORY=US-12.2
uv run pytest -m models -p no:cacheprovider --no-cov -k "us_12_" -rs
make -n eval-classification; make -n eval-drafts REVIEWS=/x/r.json; make -n evals
make -n eval-classification EVAL_PROFILE=claimcoach-evals LIMIT=3 WORKER_PORT=18250
# no worker; scratch homes
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models
make eval-classification EVAL_OUT=<scratch>/out2/none
make eval-drafts EVAL_OUT=<scratch>/out2/none                       # no REVIEWS
make evals EVAL_OUT=<scratch>/out2/evals                            # no worker, no REVIEWS
uv run python -I <scratch>/mkreviews.py <scratch>/reviews           # 7/10, 6/10, bad key
python3 - <<EOF   # cut-quarter.json: final = the first 75% of the draft's words
...
EOF
for f in pass-7-of-10 block-6-of-10 cut-quarter bad-key missing; do
  make eval-drafts REVIEWS=<scratch>/reviews/$f.json EVAL_OUT=<scratch>/out2/$f
  uv run python -m claimcoach.evals drafts --reviews <scratch>/reviews/$f.json --out <scratch>/out2/direct-$f; echo $?
done
# scratch loopback worker over fake models on 18217 (see the US-12.1 report)
export HERMES_HOME=<scratch>/w/hermes MODELS_HOME=<scratch>/w/models
make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good
make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/nopdf DENIAL_SET=<scratch>/nopdf.json
make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/limit LIMIT=3
make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/limit LIMIT=0
make case-list WORKER_PORT=18217
```

```text
$ make test-story STORY=US-12.2
===================== 19 passed, 1674 deselected in 9.36s ======================
$ make evidence STORY=US-12.2
===================== 19 passed, 1674 deselected in 9.10s ======================
junit.xml: tests=19 failures=0 errors=0 skipped=0 timestamp=2026-10-31T22:37:44
$ uv run pytest -m models -k us_12_ -rs
SKIPPED [4] tests/fakes/evals.py:176: no ClaimCoach worker on port 18200; start it with make start

$ make -n eval-drafts REVIEWS=/x/r.json
[ -n "$REVIEWS" ] || { echo "not measured: make eval-drafts REVIEWS=<the manager's draft reviews (JSON)>"; exit 2; }
uv run python -m claimcoach.evals drafts --reviews "$REVIEWS" --out "$EVAL_OUT"
$ make -n evals
failed=; for gate in eval-redaction eval-classification eval-drafts eval-latency eval-egress; do \

$ make eval-drafts REVIEWS=<scratch>/reviews/pass-7-of-10.json EVAL_OUT=<scratch>/out2/pass-7-of-10
US-12.2 draft_acceptance: acceptance_rate 0.7000 (7/10), target 0.70: PASS
  coding_error               0.5000 (1/2)
  eligibility                0.5000 (1/2)
  medical_necessity          1.0000 (2/2)
  prior_authorization        1.0000 (2/2)
  timely_filing              0.5000 (1/2)
  missed r07:coding_error
  missed r08:timely_filing
  missed r09:eligibility
report: <scratch>/out2/pass-7-of-10/US-12.2/draft-acceptance.json
direct CLI exit=0
$ make eval-drafts REVIEWS=<scratch>/reviews/block-6-of-10.json ...
US-12.2 draft_acceptance: acceptance_rate 0.6000 (6/10), target 0.70: BLOCKED
  ...
  missed r06:prior_authorization
make: *** [eval-drafts] Error 1
direct CLI exit=1
$ make eval-drafts REVIEWS=<scratch>/reviews/cut-quarter.json ...
US-12.2 draft_acceptance: acceptance_rate 0.0000 (0/1), target 0.70: BLOCKED
  coding_error               0.0000 (0/1)
  missed r00:coding_error
make: *** [eval-drafts] Error 1
direct CLI exit=1
$ make eval-drafts REVIEWS=<scratch>/reviews/bad-key.json ...
not measured: eval set <scratch>/reviews/bad-key.json is missing or not a valid eval set
make: *** [eval-drafts] Error 2
direct CLI exit=2

$ make evals EVAL_OUT=<scratch>/out2/evals          # no worker, no REVIEWS
== eval-redaction
not measured: the worker on port 18200 answered worker_unavailable
== eval-classification
not measured: the worker on port 18200 answered worker_unavailable
== eval-drafts
not measured: make eval-drafts REVIEWS=<the manager's draft reviews (JSON)>
== eval-latency
not measured: the worker on port 18200 answered worker_unavailable
== eval-egress
not measured: the worker on port 18200 answered worker_unavailable
release blocked by: eval-redaction eval-classification eval-drafts eval-latency eval-egress
make: *** [evals] Error 1

$ make eval-classification WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good
US-12.2 classification_accuracy: accuracy 0.7500 (15/20), target 0.85: BLOCKED
  bundling                   0.5000 (1/2)
  coding_error               1.0000 (2/2)
  ...
  missed denial_006:medical_necessity
  missed denial_009:missing_information
  missed denial_012:duplicate_claim
  missed denial_015:non_covered_service
  missed denial_018:bundling
report: <scratch>/out2/good/US-12.2/classification-accuracy.json
make: *** [eval-classification] Error 1
$ make eval-classification ... DENIAL_SET=<scratch>/nopdf.json
US-12.2 classification_accuracy: accuracy 1.0000 (14/14), target 0.85: PASS
$ make eval-classification ... LIMIT=3
US-12.2 classification_accuracy: accuracy 1.0000 (3/3), target 0.85: PASS
$ make eval-classification ... LIMIT=0
python -m claimcoach.evals classification: error: argument --limit: must be a whole number of 1 or more
$ make case-list WORKER_PORT=18217   (summarized)
64 cases; unpurged: 0 ; with documents: 0 ; diagnosed/drafted: 0
```

Artifacts: `evidence/US-12.2/junit.xml`

## Failures

None.

## Notes

- Rows 8 and 9 are **UNVERIFIED**. No worker runs, and I did not start the real one; as
  instructed, I made no model download, no `models.yaml` edit, and no `~/.hermes` change. The
  user's `models.yaml` fails validation, and no manager review file exists. There is no
  `classification-accuracy.json` or `draft-acceptance.json` in `evidence/US-12.2/`: operator
  reports went to scratch `EVAL_OUT` folders.
- Rows 1 and 2 ran on fake models. The 0.75 and 1.0 figures measure the gate, not Bonsai or Qwen.
- The default denial set is synthetic and labeled by construction. Its provenance says it still
  awaits a billing manager's review, so the SPECS Given "a labeled de-identified eval set" is met
  only in that synthetic sense until a partner set replaces it. I exercised the `DENIAL_SET=`
  override with a subset file.
- `test_us_12_2_classification_on_real_models` asserts only that the exit code matches
  `report.passed`, not that the run reaches 85%. US-12.1's real-model test does assert `passed`.
  Harmless, since the CLI is the gate, but the two differ.
- The code changed while I was testing. The draft rubric became two-sided (a cut draft fails),
  `eval-drafts` joined `make evals` even without `REVIEWS`, and the no-`REVIEWS` message changed
  from `usage: ...` to `not measured: ...`. I re-ran everything on the updated code; this report
  records that second round (see the US-12.1 report Notes for the timeline).
- Exit codes through Make: `make` returns 2 for any failed recipe, so `make eval-drafts` with a
  6/10 file and with a bad file both end with shell status 2. Only the CLI's own code, printed as
  `Error 1` / `Error 2`, tells them apart, yet the runbook gives 0/1/2 for "every command".
