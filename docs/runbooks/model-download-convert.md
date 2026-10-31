# Runbook: Model download and reranker conversion

Story: US-2.4. Rules: BR-1 (the only outbound calls are downloads the user confirmed), BR-11
(weights live under `MODELS_HOME` and are read in place, never copied).

ClaimCoach never downloads on its own. A download or conversion runs only for a request with
`confirm: true`, sent by the settings page after the user says yes, or by an operator with
`CONFIRM=yes`. `confirm: false` returns `declined` and starts nothing.

## Preconditions

- The worker is running ([worker-start-stop-health](worker-start-stop-health.md)).
- The `mlx-lm` venv has `hf` and `mlx_lm.convert` (the `acquire` commands in `models.yaml`):

  ```bash
  uv venv --python 3.12 ~/Models/.venvs/mlx-lm
  uv pip install --python ~/Models/.venvs/mlx-lm/bin/python mlx-lm huggingface_hub
  ```

- Free disk under `MODELS_HOME` for the model (PRD §8: 8B ≈ 5 GB, 14B ≈ 8 GB, 27B ≈ 9 GB; the
  reranker source is ≈ 16 GB until converted).
- Converting the reranker needs ~16 GB of free memory; the worker refuses (`model_busy`) while any
  ClaimCoach model server is resident, and while it converts every model load waits (`queued`).
- Requests must be JSON with `"confirm": true` as a JSON boolean; `"yes"`, `1`, or a form post is
  `invalid_request`.

## Steps

1. See what is missing (offline; `weights: missing` and, for `rerank`, `source_present`):

   ```bash
   make models-check
   make models-status
   ```

2. Download a missing role's model into `MODELS_HOME/<model_dir>` after confirming:

   ```bash
   make models-download ROLE=explanation CONFIRM=yes
   ```

   The answer is `started` (job running), `in_progress`, or `present`. Progress shows as
   `acquire: downloading` in `make models-status`; output goes to
   `~/.hermes/plugin-data/claimcoach/models/acquire-<role>.log` (mode `0600`).

3. For the reranker, download the official source first, then convert it locally to MLX 4-bit.
   Conversion runs with `HF_HUB_OFFLINE=1`; it needs no network:

   ```bash
   make models-download ROLE=rerank CONFIRM=yes   # Qwen/Qwen3-Reranker-8B → Qwen3-Reranker-8B
   make models-convert CONFIRM=yes                 # → Qwen3-Reranker-8B-MLX-4bit
   ```

4. Record what was fetched (repo and revision) for the audit trail:

   ```bash
   cat ~/Models/<model_dir>/.cache/huggingface/download/*.metadata 2>/dev/null | head
   ```

## Verification

```bash
make models-status
```

- The role reports `"weights": "present"` and `"acquire": null`.
- For the reranker, `~/Models/Qwen3-Reranker-8B-MLX-4bit/config.json` has a `quantization` block
  with `"bits": 4`.
- A sharded model is `present` only when every shard listed in `model.safetensors.index.json`
  exists, so an interrupted download stays `missing` and the next confirmed download resumes it.
- `acquire: "failed"` means the job exited non-zero or left no weights; read
  `acquire-<role>.log`, fix the cause (disk, venv, network), and repeat the step. `hf download`
  resumes partial files.

## Rollback

- Delete only the directory this runbook created under `MODELS_HOME`
  (`~/Models/<model_dir>`, and for the reranker also `~/Models/Qwen3-Reranker-8B` once the
  converted model is verified). Other apps share `~/Models`: never remove anything ClaimCoach did
  not download.
- A role whose directory is removed reports `weights: missing` again; nothing else changes.
