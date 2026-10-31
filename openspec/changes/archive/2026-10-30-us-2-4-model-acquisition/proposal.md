# Proposal: US-2.4 Missing-Model Detection, Confirmed Download, and Reranker Conversion

## Why

A fresh Mac will be missing most of the seven models. The biller must see what is missing and
fetch it only after saying yes: model downloads are the one outbound network call ClaimCoach is
allowed (BR-1, PRD §8, §10). The reranker has no ready MLX build, so it is converted locally.

## What Changes

- Model status reports per role `weights: present | missing` (config plus at least one
  `*.safetensors` under the model dir), `venv_present`, and for converted roles `source_present`.
- Add `claimcoach.models.acquire.Acquirer`: `download(DownloadRequest)` runs
  `hf download <repo> --local-dir $MODELS_HOME/<dir>`; `convert(ConversionRequest)` runs
  `mlx_lm.convert --hf-path <source> --mlx-path <target> -q --q-bits 4` with `HF_HUB_OFFLINE=1`.
  Both run as background jobs; status shows `downloading` / `converting` / `failed`.
- Requests carry a required `confirm: bool`. `confirm: false` returns `declined` without starting
  any process; a present model returns `present` without network.
- Routes: worker and gateway `POST /models/download`, `POST /models/convert`; the gateway
  validates the body itself so a bad body never echoes back.
- New error code `conversion_unavailable` (409). Runbook `model-download-convert.md` filled in;
  Makefile `models-download ROLE=… CONFIRM=yes`, `models-convert CONFIRM=yes`.

## Capabilities

### New Capabilities
- `model-acquisition`: missing-model detection, confirmed download, and local reranker conversion.

### Modified Capabilities
- None.

## Impact

- `WorkerClient` gains POST support and relays the worker's own 4xx envelope codes.
- Project `.claude/settings.json` denies `make models-download` / `models-convert` to agents.
