# Design: US-12.1 redaction recall release gate

## Context

`Redactor.redact_text` (US-3.1) unions the PHI model's spans with the regex validators' and runs a
second pass; the worker serves it at `POST /redact`, which returns the redacted text and counts
only. The synthetic set seeds each document with known PHI strings per category (`phi`), plus the
reply a perfect model would give (`model`, used by offline tests). The worker owns the models
(PC-4, BR-12), so an eval must not start model servers of its own.

## Goals / Non-Goals

Goals: one command that measures recall on the synthetic set with the real models, reports it per
category, writes the JSON evidence, and exits non-zero below 98%.

Non-Goals: precision (over-redaction is safe; PRD sets no target); a larger or real-document set
(PRD §4 names the synthetic set); running in `make check` (it needs the real PHI model).

## Decisions

1. **The eval goes through the running worker's `/redact`, not an in-process redactor.** It
   measures exactly what logs and agent results get (the full union and second pass), with the
   worker's memory guard in charge of the model. Rejected: building a `ModelManager` in the eval
   process (a second owner of ports 18200–18219 and of the memory guard).
2. **A unit is one distinct value of one category in one document, recalled when neither the
   value nor any of its distinctive words remains in the output as a whole word, in any case.**
   That is what a reader of a log would see: `[ADDRESS], Port Ellery, OR 80210` still leaks the
   town and the ZIP, and `(950) [PHONE]` the area code. A word is distinctive when the original
   document holds it only inside PHI (`Port`, `80210`), not in its prose (`or`). Whole words, so a
   two-letter surname is not "found" inside another word. A document the worker could not redact
   misses all its units and is listed under `errors` with its code. The loader refuses a set whose
   seeds do not occur in their document (they would count as redacted for free) or that lacks one
   of the seven categories. Rejected: span-offset matching (needs the original spans in a
   response, which BR-14 forbids); whole-value matching only (review finding: overstates recall).
3. **The gate is on overall recall ≥ 0.98, compared exactly as a fraction, as the Gherkin
   states; per-category recall is reported, not gated.** The four-place `value` is for display:
   440/449 shows 0.98 and blocks. A category far below target still shows on the first lines of the
   output and in the JSON. Rejected: a per-category floor (stricter than NFR-4 and the scenario,
   which says "recall is 98% or higher" → exit 0).
4. **Exit codes: 0 met, 1 missed (blocked), 2 not measured.** A worker that is down or a set that
   does not load must not read as "below target" or as a pass; `make release-gate` stops on both.
5. **Evals live in `plugin/claimcoach/evals/` (SPECS' `evals/redaction_recall.py`).** They are
   then typed, linted, and covered at 100% with the app (ES-1, ES-4) and import the app's models.
   The gateway never imports them.
6. **The report holds IDs, categories, and numbers only (BR-14)**, so the JSON can be committed
   as evidence; a test checks that no seeded value appears in it.

## Risks / Trade-offs

- [The synthetic set is small (12 documents, ~100 units): one miss is ~1%] → the per-unit misses
  are listed, so a regression is visible at once; the set can grow without code changes.
- [A model that rewrites text could "remove" PHI by mangling the document] → `/redact` replaces
  spans only; the second pass and placeholders are deterministic.
