# Design: US-9.1 code and payer-rule tools

## Context

Hermes calls a tool handler synchronously in the gateway process and expects a JSON string
(PC-8). The global corpus is a SQLite store the worker owns (PC-4: the gateway only proxies). The
guard (US-3.2) already reaches the worker from a handler through its own thread and event loop.
Code entries are stored by key (`CARC/197`, `RARC/N286`, `GROUP/CO`); rule cards match a payer by
leading words (US-6.2 design decision 4).

## Goals / Non-Goals

Goals: typed, PHI-free answers from the global corpus, with provenance and the stale flag, for
any code shape a biller types.

Non-Goals: similarity search over the corpus (keys are exact); answers about a case (US-9.2).

## Decisions

1. **The worker answers; the handler proxies.** Two worker routes take the tool's own parameter
   model as the JSON body (never the URL) and answer the typed result; the handler validates the
   arguments, calls the route with `WorkerClient`, and returns `result.model_dump_json()`.
   Rejected: opening the global store in the gateway (PC-4; it would load SQLite and numpy into
   Hermes' process and race the worker's writes).
2. **Code shapes (SPECS.md open question: fixture entries).** `CO-197` is the group entry and the
   reason entry, in that order; a bare code is one entry; RARC shapes (`N…`, `M…`, `MA…`) are read
   before CARC shapes because no CARC starts with M or N; a numeric CARC loses leading zeros. A
   code that has no shape, or no stored entry, is `code_not_found`. Tests use fixture entries
   imported through US-4.3's `import_bundle`, which is the final import format. Rejected: a fuzzy
   search (it would answer a different code with confidence).
3. **Errors are fixed envelopes.** `code_not_found` and `payer_not_found` join `ErrorCode` with
   fixed messages and are relayed by the client (404); a worker that is down or slower than the
   call's timeout is `worker_unavailable`. The asked payer name is never echoed: the result names
   the payer as its cards do. Rejected: `ok: true` with an empty list (the agent would read it as
   "the payer has no rules").
4. **Reference text is capped at 4000 characters per entry, flagged `truncated`.** A result then
   always fits one `/redact` call (200 000 characters), so the guard never fails closed on size.
   Rejected: no cap (a 200 000-character card would make the tool answer `redaction_failed`).
5. **`run_blocking` is the guard's runner, generalised.** One bounded, daemon-thread runner serves
   the redaction and the tool call. Rejected: `is_async=True` registration (Hermes would await the
   handler, but the guard is sync by design and is shared with the hook).

## Risks / Trade-offs

- [The guard runs the PHI model over reference text, which may redact a word in it] → the text is
  global reference material; a redacted word is a cosmetic loss, never a leak.
- [A cut card may hide its end] → `truncated: true`, and the pane shows the full card.
