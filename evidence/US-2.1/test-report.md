# Test Report: US-2.1 Model Role Registry in models.yaml

Change: us-2-1-model-registry
Story: US-2.1
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Every PRD role is registered: Then it contains the roles extraction, phi_detection, classification, embedding, rerank, explanation, drafting, and transcription" | PASS | `test_us_2_1_every_role_registered` loads the packaged `models.default.yaml` into `ModelRegistry` → exactly the eight roles; `test_us_2_1_missing_role_rejected` → a file without `drafting` fails with `models.yaml: roles: missing roles: drafting`; `make models-check` lists eight rows |
| 2 | "Model directories resolve under MODELS_HOME: Then every model path is inside MODELS_HOME and no weight file is copied" | PASS | `test_us_2_1_paths_resolve_under_models_home` (`MODELS_HOME` = test dir): every `model_path` and server argv path is inside it; an inode+mtime snapshot of `MODELS_HOME` is unchanged after resolving, presence checks, and argv building; the data dir holds no `*.safetensors`. `test_us_2_1_escaping_paths_rejected` (4 cases: absolute, `..`, `~`, `a/../b`) and `test_us_2_1_escaping_source_dir_rejected` → validation errors naming the entry |
| 3 | "Ports outside the app range are rejected: Then loading fails with a validation error naming that entry and the allowed range 18200-18219" | PASS | `test_us_2_1_ports_outside_range_rejected` → `models.yaml: roles.classification.port: port 18300 is outside the allowed range 18200-18219`; `make models-check` on that file prints the same line and exits 1 (below); `test_us_2_1_worker_port_reserved` → 18200 is refused as the worker's port |

## Evidence Commands

```bash
make evidence STORY=US-2.1
D=$(mktemp -d); uv run python -m claimcoach.models check --data-dir "$D"     # real ~/Models
ls -la "$D"
D=$(mktemp -d); uv run python -m claimcoach.models init --data-dir "$D"
sed -i '' 's/port: 18202/port: 18300/' "$D/models.yaml"
uv run python -m claimcoach.models check --data-dir "$D"; echo "exit=$?"
```

```text
====================== 38 passed, 225 deselected in 0.86s ======================

MODELS_HOME=/Users/josoroma/Models
extraction     18201   8B  missing  venv ok          Qwen3-VL-8B-Instruct-4bit
phi_detection  18202   8B  missing  no venv mlx-lm   Qwen3-8B-4bit
classification 18202   8B  missing  no venv mlx-lm   Qwen3-8B-4bit
embedding      18203   8B  missing  no venv mlx-lm   Qwen3-Embedding-8B-4bit-DWQ
rerank         18204   8B  missing  no venv mlx-lm   Qwen3-Reranker-8B-MLX-4bit
explanation    18205  14B  missing  no venv mlx-lm   Qwen3-14B-4bit
drafting       18206  27B  present  venv ok          Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed
transcription  18207  24B  missing  venv ok          Voxtral-Small-24B-2507-4bit
-rw-r--r--  models.yaml      (the only file written: into the data dir, not MODELS_HOME)

error: models.yaml: roles.phi_detection.port: port 18300 is outside the allowed range 18200-18219
models.yaml: roles.classification.port: port 18300 is outside the allowed range 18200-18219
exit=1
```

Artifacts: `evidence/US-2.1/junit.xml`

## Failures

None.

## Notes

- Against the real `~/Models` only Bonsai (drafting) is present; the PRD's `mlx-lm` venv does not
  exist on this Mac yet, which `models-check` reports instead of hiding. Creating it is in
  `docs/runbooks/model-download-convert.md`.
- Roles that run the same server share a port (phi_detection and classification → one Qwen3-8B,
  `test_us_2_1_shared_server_roles`); two roles naming one port with different servers are
  rejected (`test_us_2_1_conflicting_shared_port_rejected`).
- Every server command must contain `{host}` (`mlx_vlm.server` binds `0.0.0.0` by default);
  `test_us_2_1_invalid_entries_named[command-without-host]`.
- After review: a sharded model is `present` only when every shard in
  `model.safetensors.index.json` exists (`test_us_2_1_sharded_model_needs_every_shard[5]`); the
  real Bonsai directory still reads `present`.
- `make models-*` validates `ROLE` against the enum before any shell runs;
  `test_us_2_1_makefile_roles_match_the_enum` keeps the two lists in sync.
