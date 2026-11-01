# Design: US-13.3 Data, API, Storage, and Upload Reference

## Context

The reference must stay exact: a wrong limit or a missing route misleads more than no reference at all.

## Goals / Non-Goals

- Goals: a page that stays true to the code, checked by `make check`.
- Non-Goals: replacing the runbooks, which keep the operational detail.

## Decisions

1. Document the gateway routes in full and the worker-only routes by path. Rejected: a full worker table, which only `plugin_api.py`, the agent tools, and `make` call, with the per-launch token.
2. Read the schema from `_SCHEMA` and the case-items DDL in the test. Rejected: a hand-kept table list, which silently misses a new table.
3. Show limits in MiB as the code defines them in whole MiB, and fail if one is not. Rejected: rounding in the guide, which could state a limit the code does not enforce.

## Risks / Trade-offs

- [A route's request body changes shape] → the test checks the route set and response models; request examples are reviewed with each route change.
