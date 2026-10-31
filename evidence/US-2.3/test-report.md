# Test Report: US-2.3 Memory Guard and Queueing

Change: us-2-3-memory-guard
Story: US-2.3
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Two large models are never resident together: Then the drafting load waits until the 14B server is unloaded and the two are never resident at the same time" | PASS | `test_us_2_3_two_large_models_never_resident`: with the 14B explanation server (and an 8B) resident, `use(drafting)` evicts the idle 14B first; at the instant the 27B process is spawned the 14B process is gone and its port closed, while the 8B stays. `test_us_2_3_busy_large_server_finishes_first`: drafting is `queued` while an explanation request runs, that request completes (200), then drafting starts. `test_us_2_3_concurrent_large_loads_admit_one_at_a_time` |
| 2 | "Voxtral loads only alone: Then the job is queued and Voxtral starts only after no other ClaimCoach model server is resident" | PASS | `test_us_2_3_voxtral_loads_alone`: transcription is `queued` while classification serves a request; the idle embedding server is unloaded at once; Voxtral's process is spawned only when no other server process is alive; while Voxtral is resident a classification request is `queued` and starts after Voxtral is unloaded |
| 3 | "Queued work reports its state: Then the status reports queued" | PASS | `test_us_2_3_queued_work_reports_state`: the desktop half's path (gateway `GET /api/plugins/claimcoach/models/status` → `WorkerClient` → worker) reports drafting `"state": "queued"`, `"queued_requests": 1` while blocked, and `queued_requests: 0` after it ran. `test_us_2_3_queue_timeout`: past `queue_timeout_s` → `model_busy` (409 envelope), no drafting process spawned, role back to `unloaded` |

## Evidence Commands

```bash
make evidence STORY=US-2.3
uv run pytest tests/test_us_2_3_memory_guard.py -v --no-cov
```

```text
test_us_2_3_residency_rule[candidate0..9] PASSED (10 cases)
test_us_2_3_tiers_come_from_models_yaml PASSED
test_us_2_3_two_large_models_never_resident PASSED
test_us_2_3_busy_large_server_finishes_first PASSED
test_us_2_3_concurrent_large_loads_admit_one_at_a_time PASSED
test_us_2_3_voxtral_loads_alone PASSED
test_us_2_3_queued_work_reports_state PASSED
test_us_2_3_queue_timeout PASSED
test_us_2_3_queued_load_is_not_starved PASSED
===================== 18 passed, 245 deselected in 14.80s ======================
```

Artifacts: `evidence/US-2.3/junit.xml`

## Failures

None.

## Notes

- Residency is observed, not assumed: the tests wrap process creation and record, at each spawn,
  which server processes are alive, and assert that this equals the set of open ports.
- "Job status" (SPECS wording) is the role's status in `GET /models/status`; per-case job records
  arrive with EPIC-5 and will reuse this state.
- Fixed after independent review: new requests for a server that blocks a queued load now wait
  instead of re-pinning it (`test_us_2_3_queued_load_is_not_starved`), and a running reranker
  conversion holds back every load (`test_us_2_4_conversion_holds_back_model_loads`).
- Open question resolved (design.md decision 7): the guard counts only ClaimCoach's own servers.
  This run itself showed why the runbook step matters: another app had a Bonsai 27B server
  resident on :8080 that ClaimCoach does not see; `docs/runbooks/troubleshooting.md` step 8 tells
  the operator to check for and stop such servers under memory pressure.
- The size-tier table comes from `models.yaml` (`tier_b`, `runs_alone`,
  `residency.large_tier_b: 14`): explanation 14B, drafting 27B, transcription 24B are large;
  `test_us_2_3_tiers_come_from_models_yaml`.
