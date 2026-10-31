# Design: US-4.3 Global Corpus Import with Provenance

## Context

Three open questions: the import file formats, when a rule card is stale and how that shows, and
how the manager is identified across profiles.

## Goals / Non-Goals

**Goals:** the acceptance scenario (provenance survives import and shows in the corpus view);
strict, typed, all-or-nothing import; no network access.

**Non-Goals:** the settings-page import UI (US-10.3); de-identified example appeals (they need the
redactor in the import path; a follow-up); importing from a URL.

## Decisions

1. **Format: one YAML or JSON bundle file** (`.yaml`, `.yml`, `.json`; YAML safe-load reads both)
   with `items:`, each tagged `kind: rule_card | code | letter_template`. Every item requires
   `title`, `body`, `source`, and `verified_on` (ISO date, not in the future). Unknown fields are
   rejected (`extra="forbid"`). Max 5 MiB per file, 5,000 items. *Alternative:* CSV for codes —
   rejected for v1, it cannot carry provenance per row without a schema of its own.
2. **Stale after 180 days.** `CorpusViewItem.stale` is true when `verified_on` is more than 180
   days before today; the view and CLI show `STALE`. Payer rules change often (PRD §11), and the
   CARC/RARC lists are updated three times a year.
3. **Manager = whoever runs the import on this Mac.** The global scope holds no PHI, and access to
   the macOS account is the safeguard (PRD §10). No role check in v1. *Alternative:* a manager
   profile name in settings — deferred until US-8.2 defines the manager view.
4. **Import goes through the worker** (`hermes claimcoach corpus import FILE` validates the file
   locally, then posts it to `POST /corpus/import`), so embeddings run under the worker's memory
   guard instead of a second model server started by the CLI.
5. **Idempotent upsert.** A document ID is `kind:key` (`rule_card:<payer>/<topic>`,
   `code:<set>/<code>`, `letter_template:<template_id>`); re-importing replaces the document, its
   chunks, and its vectors. Duplicate keys inside one bundle are rejected.
6. **Local files only** (BR-1): the command reads a path; there is no URL fetch.

7. **Review outcomes.** The whole bundle is embedded in one call (one hold on the model, full
   batches); the 5 MiB cap also applies to the worker's request body; bundles must be regular
   files read with a bound; "future" and "stale" use the local date; the CLI's argparse dests are
   namespaced so they never collide with Hermes' own `command`.

## Risks / Trade-offs

- [The defaults may not match the Product Manager's intent] → recorded here and in the evidence
  notes; SPECS.md keeps the story NEEDS CLARIFICATION.
