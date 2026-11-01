# Design: US-13.5 Product README for Y Combinator

## Context

README.md is the first page an investor or practice owner reads on the repository.

## Goals / Non-Goals

- Goals: a page that stays true to the code, checked by `make check`.
- Non-Goals: replacing the runbooks, which keep the operational detail.

## Decisions

1. Product claims are copied from the PRD and tested against PRD §4; the status line says the release gates have not run against the real models. Rejected: aspirational claims (for example about BAAs) the PRD does not make.
2. Anchors are checked with GitHub's slug rule. Rejected: checking files only, which misses a renamed heading.

## Risks / Trade-offs

- [The PRD's targets change] → `test_us_13_5_targets_match_prd` fails until README.md follows.
