# Review: US-12.2

Change: us-12-2-quality-gates
Reviewer: independent `story-reviewer` agent (read-only, given the four EPIC-12 change names and the changed files, not the implementer's reasoning), 2026-10-31
Verdict: pass after fixes (both evals on real models and real manager reviews stay UNVERIFIED: no worker runs on this Mac, and no manager review file exists yet)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | `SequenceMatcher.ratio()` is symmetric, not the stated rubric: a draft with its last quarter cut scored 0.857 and passed | `similarity` is the smaller of "share of the draft kept in order" and "share of the approved letter that is the draft"; rubric restated in design decision 2, the spec, SPECS.md, and the runbook. `test_us_12_2_rubric_counts_cuts_and_additions` |
| medium | `make evals` / `make release-gate` without `REVIEWS` left out `eval-drafts` and reported every gate passed | `eval-drafts` is always one of `EVAL_GATES`; without `REVIEWS` it prints "not measured" and exits 2, so the release is blocked. Checked with `make eval-drafts` (exit 2) |
| medium | `run_case` purged only after `FlowError`/`WorkerError`: a `ValidationError`, a router exception, or Ctrl-C left the case with content, and `main` printed the traceback (case JSON) | Any other exception becomes `worker_error` and the case is purged; cancellation purges (shielded) and re-raises; `main` catches everything else and prints only its type name, exit 2. `test_us_12_3_unexpected_step_failure_is_a_code_and_still_purged`, `test_us_12_3_cancelled_flow_purges_its_case`, `test_us_12_2_unexpected_failure_names_its_type_only` |
| low | The purge warning gave a count, no case IDs or profile | Each unpurged case is named with its profile and the exact `make corpus-purge` command. `test_us_12_2_unpurgeable_cases_are_reported`, `test_us_12_4_cli_names_an_unpurged_case` |
| low | `--limit` for classification took the first n cases (two families), unlike the runbook's "round-robin" | Classification uses `benchmark_cases` like latency. `test_us_12_2_limit_runs_the_first_cases` |
| low | Accuracy was gated on the rounded value | `Score.meets` (see US-12.1) |
| low (tester) | `test_us_12_2_classification_on_real_models` checked only that the exit code matched the report, unlike the other real-model tests | It now requires the 85% gate to pass |
| low (process) | SPECS.md marked the stories DONE before their test reports existed | The reports were recorded (`evidence/US-12.x/test-report.md`) and `make evidence-check` passes before archive |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8232      0   1362      0   100%
=============== 1683 passed, 14 deselected in 238.59s (0:03:58) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-12.2
================ 2 passed, 1695 deselected in 241.92s (0:04:01) ================   (-m gate)
$ make evidence STORY=US-12.2
===================== 19 passed =====================
```

`make verify` ran once for the four EPIC-12 changes delivered together. The `models` tests skip
(no worker on this Mac); their rows are UNVERIFIED in `evidence/US-12.2/test-report.md`.
