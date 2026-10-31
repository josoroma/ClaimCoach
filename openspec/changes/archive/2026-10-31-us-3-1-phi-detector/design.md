# Design: US-3.1 PHI Span Detector with Regex Validators

## Context

PRD §8 assigns PHI span detection to Qwen3-8B plus regex validators for SSN/MRN/DOB/phone/member
ID; §11 adds a "second-pass check". The model runs in the worker (BR-2), behind the US-2.2 model
manager. Two open questions in SPECS.md are resolved here (decisions 2 and 3).

## Goals / Non-Goals

**Goals:** typed spans with a category; every seeded PHI string gone from redacted output; a
failure never yields unredacted text; offline tests over a synthetic set.

**Non-Goals:** the recall release gate itself (US-12.1 measures it); redacting images or PDFs
(text only — extraction is US-5.2); de-identification beyond the seven categories.

## Decisions

1. **The model copies values; the code finds offsets.** The prompt asks for
   `{"spans": [{"text", "category"}]}` with each value copied verbatim; `locate()` finds every
   whole-word, case-insensitive occurrence. A value that is not in the document is dropped.
   *Alternative:* ask for character offsets — rejected, 8B models miscount offsets.
2. **Open question 1 — union, not confirmation.** Regex matches are always redacted, whether or
   not the model proposed them, and a model span is never dropped because no regex confirms it.
   Recall is the release gate and a false positive only costs a placeholder. A model category
   outside the seven is kept as `other` (aliases such as `person` map to `name`).
   *Alternative:* regex only confirms model spans — rejected, it can only lower recall.
3. **Open question 2 — the second-pass check** is (a) *propagation*: every detected value, and
   each ≥ 3-letter word of a detected name, is redacted wherever else it occurs, so "Jane Doe"
   also removes "Ms. Doe" and "DOE, JANE"; then (b) a *re-scan*: after replacement the regex
   validators run over the redacted text, and anything they find is redacted too and counted in
   `second_pass_hits`. `redact(text, spans)` always runs it, so even a caller that passes only
   model spans gets regex-detectable PHI removed. *Alternative:* a second model call over the
   output — rejected for v1: doubles latency and the model is the component being checked.
4. **Fail closed.** No JSON, the wrong shape, or a truncated reply (`finish_reason: length`)
   raises `RedactionFailedError` (`redaction_failed`, 503). An unreachable or erroring server is
   `model_unavailable`. Callers never get a partially redacted text. *Alternative:* fall back to
   regex only — rejected, names and addresses would pass.
5. **Labeled validators for look-alike values.** DOB, MRN, and member ID match only after a label
   (`DOB`, `Date of Birth`, `MRN`, `Medical Record No.`, `Member ID`, `Subscriber ID`, `Policy #`
   …) and require a digit, so service dates, CARC/RARC codes, and claim numbers survive. SSN and
   phone match by shape.
6. **Chunking at 6 000 characters on line boundaries**, one model call per chunk, within one
   `use()` hold. Values are located in the whole document, so a value found in one chunk is
   redacted everywhere.
7. **Model id `default_model`.** `mlx_lm.server` serves the model it was started with under that
   id; the fake server is keyed the same way.
8. **Synthetic fixtures from a seeded generator** (`tests/fixtures/phi/generate.py`): invented
   names and towns, `555-01xx` phone numbers, every category in every document, and a test that
   the committed JSON equals the generator output.

9. **Bounded validators** (review finding, high). Every repeat between a label and its value is
   bounded (`{0,4}`), so no input backtracks for long; unbounded adjacent `\s*` runs had taken
   30 s on 400 spaces. `Redactor` runs the regex work in `asyncio.to_thread`, so the worker's
   event loop stays responsive. `test_us_3_1_validators_resist_backtracking` (10 000 characters
   after every label, < 0.5 s).
10. **Layout-tolerant location** (review finding, high). A model value also matches with its words
    in order separated by up to 8 non-word characters (a one-line address against a two-line
    block). A value that still is not found contributes its distinctive words (any with a digit,
    or 4+ letters); only a value with none of them in the document is dropped, and the count of
    such values (never the values) is logged.
11. **Wider validator coverage** (review findings). Months in any case, ordinals, `DD-MON-YYYY`,
    `(MM/DD/YYYY)` hints, `-` separators, 8-digit DOBs after a label; labels `ID`, `Mbr`,
    `Member's`, `Identification Number`, `Acct`, `Pat Acct`, `Patient Control`, `PCN`, `MR#`,
    `Medicare`, `Medicaid`, `MBI`, `HICN`, `cert`, `SS#`, snake_case keys (`member_id`,
    `date_of_birth`); spaced IDs (`XYZ 123456789`), masked (`XXX-XX-6789`) and dotted SSNs,
    10-digit phones after a label, phone extensions.
12. **Two-letter surnames in name context** (review finding). Li, Ng, Wu are redacted after a
    title (`Ms. Li`) or before a comma and another word of the same name (`LI, JANE`), not
    everywhere (they are ordinary syllables).
13. **Deadline per document** (review finding). Detection of one document is bounded by
    `total_timeout` (300 s) across chunks; past it, `redaction_failed` and the model is released.
14. **Adversarial fixtures** (review finding: tests passed by construction). The set adds an
    all-caps, column-aligned EOB with a two-line address, a two-letter surname, 40-space gaps,
    and an upper-case DOB; the fake model answers in the form a model writes (one-line address,
    one name spelling), and reports the member ID that only a table row holds.

## Risks / Trade-offs

- [Table layouts: a value under a header label in another row] → no regex can pair them; the
  model is the guard there (the fixture's table member ID is model-reported), and US-12.1
  measures recall.

- [Model misses a name that has no other occurrence] → recall is measured by US-12.1; the
  propagation pass removes every other form of each found name.
- [Over-redaction of ordinary words that match a name part] → only words of detected names, ≥ 3
  letters, whole-word; acceptable for logs and agent summaries.
- [A value split across a hard chunk cut in a > 6 000-character line] → rare in OCR'd EOB text;
  structured values are still caught by the validators.
- [Qwen3 "thinking" output] → `/no_think` in the system prompt and `<think>` blocks are stripped.
