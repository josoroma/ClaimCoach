# Proposal: Corpus CLI honors WORKER_PORT

## Why

`make worker-start WORKER_PORT=18213` starts the worker on 18213, and every `make case-*`,
`models-*`, and `worker-*` target reaches it through `WORKER_URL`. The corpus commands do not:
`claimcoach.cli` builds its worker client from `WorkerConfig`'s default port 18200, so `make
corpus-import`, `corpus-list`, `corpus-status`, `corpus-reindex`, `corpus-purge`, and
`corpus-audit` answer `error: worker_unavailable` against any other port. The independent tester
of EPIC-6 hit this against a scratch worker and had to patch the address by hand.

## What Changes

- The six worker-backed corpus subcommands (`import`, `list`, `status`, `reindex`, `purge`,
  `audit`) accept `--port`, default 18200, validated against ClaimCoach's port range 18200–18219
  (BR-11) before anything is read or sent.
- The Makefile passes `--port $(WORKER_PORT)` to them, as the other worker targets use
  `WORKER_PORT`.
- The corpus runbook says so.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `corpus-import`: the corpus commands reach the worker on the port the operator chose.

## Impact

- `hermes claimcoach corpus …` without `--port` behaves as before (18200). The local subcommands
  (`backup`, `restore`, `key-export`, `key-import`) are unchanged.
