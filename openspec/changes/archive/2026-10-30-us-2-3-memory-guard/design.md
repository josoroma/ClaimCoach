# Design: US-2.3 Memory Guard and Queueing

## Context

US-2.2 admits every start under one `asyncio.Condition`. Residency counts every server that is
`starting`, `ready`, or `stopping`: a stopping process still holds its memory until it exits.

## Goals / Non-Goals

**Goals:** BR-12 can never be violated, even by concurrent requests; a blocked request waits
instead of failing; the wait is visible and bounded.

**Non-Goals:** measuring memory used by other apps; priority between queued requests (FIFO by
condition wake-up is enough for one biller).

## Decisions

1. **The rule is a pure function of specs.** `blockers(candidate, resident)` returns the resident
   servers that must be gone first:
   - candidate `runs_alone` (Voxtral) → every resident server;
   - any resident `runs_alone` → that server;
   - candidate large (`tier_b ≥ large_tier_b`) → every resident large server;
   - otherwise → none.
   Being pure, it is tested exhaustively without processes.
2. **Admission reserves residency.** The admitted server is marked `starting` before the lock is
   released, so two concurrent large loads can never both pass the check.
3. **Blocked loads evict idle blockers immediately.** Waiting for the idle sweep would make a
   drafting request wait up to ten minutes behind an idle 14B. A blocker that is in use is
   evicted the moment its last request releases it (`release` checks for queued servers it blocks).
4. **No starvation** (review finding). While a server blocks a queued load, new requests for it
   wait instead of re-pinning it, so steady 14B traffic cannot hold a drafting load until it times
   out.
5. **A conversion counts as resident** (review finding). While the reranker converts (~16 GB),
   every load queues behind it, as if a `runs_alone` server were resident.
6. **Queue timeout** (`queue_timeout_s`, default 900 s) bounds the wait; it also turns an
   accidental nested `use()` of two large roles in one task into a `model_busy` error instead of a
   deadlock.
7. **Other apps' servers are not counted** (SPECS open question). Measuring them needs process
   inspection of programs ClaimCoach does not own, and PRD §8 already budgets the interactive set
   at 13.5 GB with peaks of 22–28 GB. The troubleshooting runbook tells the operator to stop other
   apps' servers under memory pressure. Revisit if field reports show swap.

## Risks / Trade-offs

- [Embedding + reranker + 8B + 14B stay resident together] → allowed by BR-12 (only one ≥14B);
  ≈ 22 GB, inside the PRD peak.
- [A long draft blocks transcription] → transcription is a batch job run after hours (PRD §8).
