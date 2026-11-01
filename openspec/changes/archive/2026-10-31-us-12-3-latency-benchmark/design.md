# Design: US-12.3 upload-to-draft latency measurement

## Context

A case reaches an appeal-ready draft after three jobs (extract, diagnose, draft), each started by
REST and followed through job events (US-5.2). The memory guard (US-2.3) loads models in
sequence, so the first case pays for model loads the next ones may not.

## Goals / Non-Goals

Goals: the median upload-to-draft time on this Mac with real models, per-step times, a gate.

Non-Goals: concurrency (a biller works one case at a time); the biller's own review time; export
time (the target ends at the draft).

## Decisions

1. **The benchmark set is the US-12.2 denial set: 20 cases, 7 pasted 835s, 7 letter uploads, 6
   EOB PDFs (open question).** The three kinds exercise the three extraction paths (835 parser;
   the vision model over a letter; over a rendered PDF page). `benchmark_cases` takes them
   round-robin by kind, so `LIMIT=6` still times two of each. Rejected: a separate latency set
   (two sets to keep in step).
2. **A failed case counts as slower than every other one, and the gate also requires every case
   to finish.** A failure can raise the median but never lower it; `median_seconds` is `None`
   ("unbounded") when failures reach the middle. Rejected: dropping failed cases (a flaky model
   would look fast).
3. **Time is the client's monotonic clock from before the first upload to the draft job's last
   event.** It includes queueing behind the memory guard, as the biller waits for it.
4. **Cold starts count.** The first case includes model loads; the median absorbs one slow case
   in twenty, and that is the experience of the first case of a morning.

## Risks / Trade-offs

- [A run takes long] → `LIMIT`; the report lists per-step times so the slow step is visible.
- [Another app on the Mac competes for memory] → the runbook's Preconditions say to run with
  ClaimCoach alone, and the report records when it ran.
