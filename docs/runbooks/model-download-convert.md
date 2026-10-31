# Runbook: Model download and reranker conversion

Status: **skeleton** — US-2.4 fills the steps (confirmed `hf download` into `~/Models`, reranker
conversion). Rules: BR-1 (downloads only after user confirmation), BR-11 (weights read from
`MODELS_HOME`, never copied).

## Preconditions

- The worker is running ([worker-start-stop-health](worker-start-stop-health.md)).
- Free disk under `MODELS_HOME` for the model being added (PRD §8 lists sizes).
- Explicit user confirmation for every download.

## Steps

1. US-2.4: list missing models from the worker's model-status route.
2. US-2.4: confirm and download the missing model into `MODELS_HOME`.
3. US-2.4: convert the reranker to local MLX 4-bit.

## Verification

- US-2.4: the model-status route reports every role as present.

## Rollback

- Delete only the model directory that was added under `MODELS_HOME`; other apps share that
  folder, so never remove anything ClaimCoach did not download.
