# Design: US-2.4 Missing-Model Detection, Confirmed Download, and Reranker Conversion

## Context

`hf` and `mlx_lm.convert` ship in the model venvs. A download is several GB and takes minutes,
far longer than the gateway's 5 s worker timeout.

## Goals / Non-Goals

**Goals:** no network without an explicit `confirm: true`; the rerank role becomes usable
through a confirmed, local conversion; progress is visible through the status the settings page
already polls.

**Non-Goals:** the settings page UI (US-10.3); integrity pinning by revision (the runbook records
the revision the operator downloaded); disk-space checks beyond the runbook precondition.

## Decisions

1. **`confirm` is a required strict boolean, not a default.** A body without it, or with `"yes"` or
   `1` (Pydantic's lax coercion, found in review), is `invalid_request`; `false` is an explicit
   decline that returns `declined` and starts nothing. *Alternative:*
   separate decline route — rejected, the settings dialog answers one question.
2. **Jobs run in the background; the request returns `started`.** The acquirer keeps one task per
   role; a second request while it runs returns `in_progress`. Status shows the job state, and
   `weights` flips to `present` when the files land. A failed job keeps `failed` until the next
   attempt; its output goes to `<data>/models/acquire-<role>.log` (0600), never to the response.
3. **Presence means `config.json` plus the weights**: every shard listed in
   `model.safetensors.index.json` when there is one, otherwise at least one `*.safetensors`. `hf`
   lands the config first and moves shards in one by one, so checking "any shard" would report a
   half-downloaded model as present (review finding). A directory a job is writing is never served.
4. **Download fetches what the role needs.** For the rerank role that is the official
   `Qwen/Qwen3-Reranker-8B` source repo; conversion is a separate confirmed step.
5. **Conversion is local and offline.** It runs with `HF_HUB_OFFLINE=1`, requires the source to be
   present and the target to be missing, and refuses (`model_busy`) while any ClaimCoach model
   server is resident, because converting an 8B in bf16 needs ~16 GB.
6. **The gateway validates bodies itself.** Hermes owns the FastAPI app, so its default 422 (which
   echoes input) cannot be replaced; the route reads the raw body and answers `invalid_request`
   with the envelope. It accepts only `Content-Type: application/json`, so a cross-site form or
   `text/plain` POST cannot start a download (defense in depth behind Hermes' own auth).
8. **Jobs are keyed by target directory**, not role: phi_detection and classification share one
   model dir and must never run two downloads into it; a failure marks every role sharing it.
7. **Agents cannot trigger downloads.** `.claude/settings.json` denies the download/convert make
   targets; only a person runs them.

## Risks / Trade-offs

- [Repo IDs for community builds can move] → they are data in `models.yaml`, editable without code.
- [A download fills the disk] → runbook precondition; `hf` resumes after the operator frees space.
