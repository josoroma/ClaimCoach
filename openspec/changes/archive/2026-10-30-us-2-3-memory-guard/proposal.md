# Proposal: US-2.3 Memory Guard and Queueing

## Why

The M3 Pro has 36 GiB shared by macOS, Hermes, and every app. Two ≥14B models, or Voxtral next to
anything, would push it into swap or kill a process mid-draft. Loads that would break the rule
must wait instead (SPECS.md US-2.3, PRD §8, §11, BR-12).

## What Changes

- Add `claimcoach.models.memory_guard` with `MemoryGuard.blockers(candidate, resident)`: a pure
  rule over the size-tier table derived from `models.yaml` (`tier_b`, `runs_alone`) and the
  `ResidencyPolicy` (`large_tier_b`, default 14).
- `ModelManager` asks the guard before every start. A blocked load is `queued`: idle blockers are
  unloaded at once, busy blockers are unloaded as soon as their last request ends, and the load
  starts when nothing blocks it. A load queued longer than `queue_timeout_s` fails with
  `model_busy`.
- `ModelStatus` reports `queued` and `queued_requests`, which the desktop half polls through
  `GET /api/plugins/claimcoach/models/status`.
- Troubleshooting runbook: memory-pressure section.

## Capabilities

### New Capabilities
- `memory-guard`: residency rules between ClaimCoach model servers and queueing of blocked loads.

### Modified Capabilities
- None.

## Impact

- Only ClaimCoach's own servers are counted (open question resolved in design.md).
