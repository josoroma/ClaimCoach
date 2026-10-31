# Design: US-2.1 Model Role Registry

## Context

PRD §8 lists seven models for eight roles and says each role has a model dir under `MODELS_HOME`,
a venv, a command, and a port. `~/Models` on this Mac stores each repository flat under its repo
name (`DOWNLOAD-MANIFEST.json`: `local_dir = <repo name>`) and venvs under `~/Models/.venvs/`.

## Goals / Non-Goals

**Goals:** one typed source of truth for every model the app runs; invalid files fail before any
process starts, with a message naming the entry; paths that cannot escape `MODELS_HOME`.

**Non-Goals:** starting servers (US-2.2), residency rules (US-2.3), downloads (US-2.4).

## Decisions

1. **Roles are an enum, the file maps role → spec.** `ModelRegistry.roles: dict[ModelRole,
   ModelSpec]` and a validator requiring all eight roles. *Alternative:* a list of entries — rejected,
   duplicate roles would need a separate check.
2. **Roles that run the same server share a port.** PHI detection and classification both use
   Qwen3-8B-4bit. Two roles may name the same port only if model dir, venv, and command are
   identical; the manager then runs one process (the PRD §8 budget of ≈13.5 GB assumes one 8B).
   *Alternative:* one server per role — rejected, doubles memory for no gain.
3. **Paths are validated lexically, never resolved.** `model_dir` must be relative with no `..`;
   `ModelSpec.model_path(home)` is `home / model_dir`. Resolving symlinks would reject a user who
   symlinks a model into `~/Models`, and nothing is ever copied.
4. **Command templates with a closed placeholder set** `{venv} {model} {host} {port}`; every
   serving command must contain `{host}` and `{port}`. `mlx_vlm.server` defaults to `0.0.0.0`, so a
   command that forgot `--host` would expose a model server on the LAN.
5. **Port 18200 is reserved for the worker**; model servers use 18201–18219.
6. **Converted roles declare `convert` instead of `repo_id`** (exactly one of the two). The rerank
   role downloads `Qwen/Qwen3-Reranker-8B` into `Qwen3-Reranker-8B` and converts it to
   `Qwen3-Reranker-8B-MLX-4bit` (US-2.4).
7. **The default file is package data, written once.** `ensure_registry_file` writes it with
   `O_EXCL` so a user's edits are never overwritten. *Alternative:* load defaults in code and
   merge — rejected, two sources of truth.
8. **REST-facing types live in `claimcoach.models.types`** with no YAML import, so the gateway
   (PC-4) can import them without the worker's dependencies.
9. **Default idle timeout 600 s, queue timeout 900 s, start timeout 300 s** (US-2.2 open
   question): long enough to keep the interactive set warm across a case, short enough to free
   memory between cases. All three are editable in `models.yaml`.

## Risks / Trade-offs

- [Embedding/rerank serving commands are provisional] → `mlx_lm.server` is the default for both;
  EPIC-4 (retrieval) may change the command without touching the schema.
- [`mlx_audio.server` in the shared `mlx-vlm` venv fails to import `webrtcvad` on this Mac] →
  transcription is v1.1 (EPIC-11); status reports the server unhealthy instead of hiding it.
- [The venv names follow PRD §8 (`mlx-lm`), which does not exist yet on this Mac] → model status
  reports `venv_present: false`; the runbook shows how to create it.
