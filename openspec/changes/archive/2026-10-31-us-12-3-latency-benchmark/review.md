# Review: US-12.3

Change: us-12-3-latency-benchmark
Reviewer: independent `story-reviewer` agent (read-only, given the four EPIC-12 change names and the changed files, not the implementer's reasoning), 2026-10-31
Verdict: pass after fixes (the benchmark on the M3 Pro with real models stays UNVERIFIED: no worker runs on this Mac)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | An unexpected exception or Ctrl-C skipped the purge of the running eval case | `run_case` purges on every outcome (see US-12.2). `test_us_12_3_unexpected_step_failure_is_a_code_and_still_purged`, `test_us_12_3_cancelled_flow_purges_its_case`, `test_us_12_3_purge_failure_is_reported` (worker and other errors) |
| low | Unpurged cases were counted, not named | `run_latency` returns their worker case IDs; the CLI names each with its profile |

Also checked and found sound by the reviewer: the median with failures counted as infinitely slow (odd and even counts), the "every case finished" condition, the round-robin benchmark mix, and that cases run one at a time (BR-12).

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8232      0   1362      0   100%
=============== 1683 passed, 14 deselected in 238.59s (0:03:58) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-12.3
================ 2 passed, 1695 deselected in 241.92s (0:04:01) ================   (-m gate)
$ make evidence STORY=US-12.3
===================== 20 passed =====================
```

`make verify` ran once for the four EPIC-12 changes delivered together. The `models` tests skip
(no worker on this Mac); their rows are UNVERIFIED in `evidence/US-12.3/test-report.md`.
