# Test Report: US-12.3 Upload-to-Draft Latency Measurement

Change: us-12-3-latency-benchmark
Story: US-12.3
Verdict: pass
Coverage: 2/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; no ClaimCoach worker running (`make worker-status`: `not running`); the user's `~/.hermes/plugin-data/claimcoach/models.yaml` fails validation (`python -m claimcoach.models check`)

## Acceptance Criteria Evaluated

Row 1 checks the SPECS.md scenario's Then clause (the benchmark's reporting and its gate) on fake
models. Row 2 is the extra scenario from the change spec. Row 3 is the scenario as written, with
"real local models" on this M3 Pro, and was not run (see Notes). The code tested is the plugin as
of 22:29 and the tests as of 22:37.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Latency benchmark reports the median: Then it reports the median duration and exits non-zero if the median exceeds 10 minutes" | PASS | `test_us_12_3_latency_reports_median` passes: `--limit 6` covers all three kinds, the target is 600 s, each case's upload, extract, diagnose, and draft times add up to its total, and the first line reads `... over 6 cases, target 600 s: PASS`. `test_us_12_3_median_over_target_blocks` passes: a clock that adds 200 s per step makes each case 800 s, so the median is 800, `passed: false`, exit 1, `BLOCKED`. Operator run: `make eval-latency WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good` against a scratch loopback worker over fake models printed `US-12.3 latency: median 0.2 s over 20 cases, target 600 s: PASS`, one line per case (`denial_001 era_835 0.1 s`, ...), and the report path, then exited 0. `latency.json` has `target_seconds: 600.0`, `median_seconds: 0.165`, and per-case `stages {upload, extract, diagnose, draft}` (e.g. `denial_003 [eob_pdf] 0.196 s`). `LIMIT=6` ran denial_001 to 006 (era_835, letter, eob_pdf, twice) |
| 2 | "Failures never lower the median (change spec): THEN it counts as slower than every finished case and the gate fails" | PASS | `test_us_12_3_failed_cases_count_as_slowest` passes: `[10, failed, 30]` gives a median of 30, and `[10, failed]` is unbounded. `test_us_12_3_a_failed_case_fails_the_gate` passes: when the drafting fake answers with no letter, the case gets `error_code: drafting_failed`, `median_seconds: null`, `passed: false`, and the line `median unbounded over 1 cases`. These failure and purge tests pass too: `_job_that_never_ends_times_out`, `_a_finished_job_that_did_not_succeed_fails` x4, `_refused_step_is_its_error_code`, `_purge_failure_is_reported` x2, `_unexpected_step_failure_is_a_code_and_still_purged`, `_cancelled_flow_purges_its_case`, and `_benchmark_names_unpurged_cases` |
| 3 | "Latency benchmark reports the median: Given a set of synthetic denial cases and real local models" (the median on this M3 Pro, `test_us_12_3_latency_on_this_mac`, marked `models`) | UNVERIFIED | `uv run pytest -m models -k us_12_` reported `SKIPPED ... no ClaimCoach worker on port 18200`. With no worker, `make eval-latency` printed `not measured: the worker on port 18200 answered worker_unavailable` (exit 2). No real median exists |

## Evidence Commands

```bash
make test-story STORY=US-12.3
make evidence STORY=US-12.3
uv run pytest -m models -p no:cacheprovider --no-cov -k "us_12_" -rs
make -n eval-latency
# no worker; scratch homes
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models
make eval-latency EVAL_OUT=<scratch>/out2/none
# scratch loopback worker over fake models on 18217 (see the US-12.1 report)
export HERMES_HOME=<scratch>/w/hermes MODELS_HOME=<scratch>/w/models
make eval-latency WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good
make eval-latency WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/limit LIMIT=6
python3 -c '<print latency.json without cases, and cases[2]>'
make case-list WORKER_PORT=18217
```

```text
$ make test-story STORY=US-12.3
===================== 19 passed, 1674 deselected in 10.13s =====================
$ make evidence STORY=US-12.3          # after the 22:37:52 test edit added _benchmark_names_unpurged_cases
===================== 20 passed, 1675 deselected in 10.90s =====================
junit.xml: tests=20 failures=0 errors=0 skipped=0 timestamp=2026-10-31T22:37:54
$ uv run pytest -m models -k us_12_ -rs
SKIPPED [4] tests/fakes/evals.py:176: no ClaimCoach worker on port 18200; start it with make start

$ make -n eval-latency
uv run python -m claimcoach.evals latency --out "$EVAL_OUT" --port 18200 --set "$DENIAL_SET" ${EVAL_PROFILE:+--profile "$EVAL_PROFILE"} ${LIMIT:+--limit "$LIMIT"}
$ make eval-latency          # no worker
not measured: the worker on port 18200 answered worker_unavailable
make: *** [eval-latency] Error 2

$ make eval-latency WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good
US-12.3 latency: median 0.2 s over 20 cases, target 600 s: PASS
  denial_001       era_835                0.1 s
  denial_002       letter                 0.2 s
  denial_003       eob_pdf                0.2 s
  ...
  denial_020       letter                 0.2 s
report: <scratch>/out2/good/US-12.3/latency.json
{'story': 'US-12.3', 'dataset': 'synthetic-denials-v1', ..., 'target_seconds': 600.0, 'median_seconds': 0.16508352049277164, 'passed': True}
{'case': 'denial_003', 'kinds': ['eob_pdf'], 'seconds': 0.1957477500254754, 'stages': {'upload': 0.0230, 'extract': 0.0749, 'diagnose': 0.0623, 'draft': 0.0356}, 'error_code': None}

$ make eval-latency WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/limit LIMIT=6
US-12.3 latency: median 0.2 s over 6 cases, target 600 s: PASS
  denial_001 era_835 / denial_002 letter / denial_003 eob_pdf / denial_004 era_835 / denial_005 letter / denial_006 eob_pdf

$ make case-list WORKER_PORT=18217   (summarized, after the whole "good" round)
64 cases; unpurged: 0 ; with documents: 0 ; diagnosed/drafted: 0
```

Artifacts: `evidence/US-12.3/junit.xml`

## Failures

None.

## Notes

- Row 3 is **UNVERIFIED**, and it is the point of the story: we still do not know whether
  ClaimCoach meets the 10-minute median on this M3 Pro with real local models. No worker runs. As
  instructed, I did not start one, download models, edit `models.yaml`, or touch `~/.hermes`. The
  user's `models.yaml` fails validation. There is no `evidence/US-12.3/latency.json`.
- The 0.2 s median comes from fake models on in-process loopback servers. It shows that the
  benchmark drives upload, extract, diagnose, and draft over real HTTP and times each step. It is
  not a latency figure. The over-target path (exit 1) was exercised only with an injected clock
  (`test_us_12_3_median_over_target_blocks`), not by a slow run.
- The code changed while I was testing (see the US-12.1 report Notes). This report records the
  second round, on the updated code.
- Exit codes through Make: a blocked latency gate makes `make` return 2, the same status as "not
  measured". The CLI's 1 vs 2 shows only as `Error 1` / `Error 2` (see the US-12.1 report).
