# Spec Delta

## Purpose

ClaimCoach fetches models by confirmed download only; there is no local conversion.

## REMOVED Requirements

### Requirement: Reranker is converted locally
**Reason**: The reranker it built was never loaded by a case flow (US-14.1).
**Migration**: None needed: no role needs conversion. The reranker's folders under `MODELS_HOME` may be removed by hand.

## ADDED Requirements

### Requirement: No conversion route or command remains
The gateway, the worker, and the Makefile SHALL offer no model conversion: no `models/convert`
route, no `models-convert` target, and no `conversion_unavailable` error code.

#### Scenario: No conversion route or command remains
- **WHEN** the gateway's and the worker's routes and the Makefile's targets are listed
- **THEN** there is no models/convert route and no models-convert target
