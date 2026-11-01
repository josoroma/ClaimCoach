# Design: US-13.2 Developer Guide: Models, Install, Configuration, First Run, and Daily Start

## Context

The guide states facts the code already holds, so it drifts the moment a role, target, or setting changes.

## Goals / Non-Goals

- Goals: a page that stays true to the code, checked by `make check`.
- Non-Goals: replacing the runbooks, which keep the operational detail.

## Decisions

1. Drift tests read the code's own sources (`models.default.yaml`, the Makefile, `plugin.yaml`), not a copy. Rejected: a generated README (a second build step for a Markdown file, and the prose around each table would still drift).
2. Only the Makefile's first `?=` block (the environment) must be documented; per-target arguments (`ROLE`, `CASE`, …) are listed by `make` with each target. Rejected: documenting every argument, which repeats `make help`.
3. The guide names only the folders ClaimCoach reads; other folders in `~/Models` are never read. Rejected: listing the unused folders, which change with other apps.

## Risks / Trade-offs

- [A runbook and the guide disagree] → the guide links each runbook for details and its commands are tested against the Makefile.
