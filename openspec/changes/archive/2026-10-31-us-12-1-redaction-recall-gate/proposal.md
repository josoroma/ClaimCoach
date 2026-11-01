# Proposal: US-12.1 Redaction Recall Release Gate

## Why

PRD §4 sets PHI recall ≥ 98% on the synthetic set, and §10 makes the redactor's recall a
release-blocking eval (NFR-4). US-3.1 built the redactor and its synthetic PHI set
(`tests/fixtures/phi/phi_set.json`), and its tests assert "no leak" against a perfect fake model,
but nothing measures the real model's recall or blocks a release on it. This change adds the gate
and the eval scaffolding the other EPIC-12 stories reuse.

## What Changes

- New `claimcoach.evals` package:
  - `types.py`: typed `EvalResult` with per-category `Score`s (and the EPIC-12 targets and exit
    codes: 0 met, 1 missed, 2 not measured).
  - `datasets.py`: strict loaders for eval sets (`PhiEvalSet` here; the denial set and the draft
    reviews for US-12.2/12.3).
  - `redaction_recall.py`: every synthetic document through the running worker's `POST /redact`;
    recall per PHI category and overall; `score_redaction`, `run_redaction`.
  - `report.py`: the report written atomically to `evidence/US-12.x/<name>.json` and summarized
    on the terminal (verdict, per-category lines, missed `<doc>:<category>`, errors).
  - `__main__.py`: `python -m claimcoach.evals redaction --set … [--out evidence] [--port …]`.
- `make eval-redaction`, `make evals`, `make release-gate` (verify, then every eval); the
  `evals-release-gates` runbook.

## Capabilities

### New Capabilities
- `redaction-recall-gate`: measuring the redactor's PHI recall on the synthetic set, per category,
  and blocking a release below 98%.

### Modified Capabilities
- None.

## Impact

- No new dependency. The eval talks to the worker over loopback with the launcher-recorded token
  (`port_client`), exactly like the corpus and agent commands.
- `evidence/US-12.1/redaction-recall.json` is evidence (ES-5); it holds IDs, categories, and
  numbers only.
