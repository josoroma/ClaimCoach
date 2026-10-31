# Test Report: US-2.4 Missing-Model Detection, Confirmed Download, and Reranker Conversion

Change: us-2-4-model-acquisition
Story: US-2.4
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Missing models are reported: Then that role is reported as missing" | PASS | `test_us_2_4_missing_models_reported`: with the explanation and rerank dirs absent, the settings page's call (`GET /api/plugins/claimcoach/models/status` through the gateway) reports both `"weights": "missing"`, rerank `source_present: false`, all others `present`; `test_us_2_1_presence_needs_config_and_weights` (a dir with `config.json` but no weights is still missing); live `make models-check` on the real `~/Models` → 7 roles `missing`, drafting `present` |
| 2 | "Download requires confirmation: Then the worker runs hf download into MODELS_HOME and the role is reported present on success" | PASS | `test_us_2_4_download_requires_confirmation`: `{"confirm": true}` → `started`; the download tool ran exactly once with `download mlx-community/Qwen3-14B-4bit --local-dir $MODELS_HOME/Qwen3-14B-4bit`; status then `weights: present`, `acquire: null`; a second request → `present`, no second run. `test_us_2_4_missing_confirmation_flag[4]`: no `confirm`, a non-boolean, or a bad body → 422 `invalid_request` from gateway and worker, PHI in the body never echoed, nothing spawned. `test_us_2_4_default_commands_use_the_model_venv`: the shipped template is `$MODELS_HOME/.venvs/mlx-lm/bin/hf download <repo> --local-dir <dir>` |
| 3 | "Declined download makes no network call: Then no outbound network connection is opened" | PASS | `test_us_2_4_declined_download_no_network`: `{"confirm": false}` for download and conversion → `declined`; the autouse socket guard (fails on any non-loopback connect or DNS lookup) stayed silent and the process spy recorded zero spawned processes, so no download tool ran either |
| 4 | "Reranker is converted locally: Then mlx_lm.convert produces the 4-bit MLX directory under MODELS_HOME and the rerank role is reported present" | PASS | `test_us_2_4_reranker_converted_locally`: source `Qwen3-Reranker-8B` present, target absent; confirmed conversion ran `convert --hf-path $MODELS_HOME/Qwen3-Reranker-8B --mlx-path $MODELS_HOME/Qwen3-Reranker-8B-MLX-4bit -q --q-bits 4` with `HF_HUB_OFFLINE=1`; the target has a 4-bit quantization config and rerank reports `present`. `test_us_2_4_source_missing[2]` → 409 `conversion_unavailable`, nothing spawned; `test_us_2_4_conversion_waits_for_resident_models` → `model_busy` while a model server is resident |

## Evidence Commands

```bash
make evidence STORY=US-2.4
uv run pytest tests/test_us_2_4_model_acquisition.py -v --no-cov
make models-check                     # real ~/Models, read-only
```

```text
test_us_2_4_missing_models_reported PASSED
test_us_2_4_download_requires_confirmation PASSED
test_us_2_4_missing_confirmation_flag[body0..5] PASSED (6 cases, incl. "yes" and 1)
test_us_2_4_gateway_accepts_only_json_bodies[3] PASSED
test_us_2_4_declined_download_no_network PASSED
test_us_2_4_reranker_converted_locally PASSED
test_us_2_4_source_missing[rerank|explanation] PASSED
test_us_2_4_client_relays_worker_codes[4] / does_not_relay_other_errors[3] PASSED
====================== 35 passed, 228 deselected in 5.72s ======================
```

Artifacts: `evidence/US-2.4/junit.xml`

## Failures

None.

## Notes

- The download and conversion tools in the tests are `tests/fakes/fake_hf.py`, which records its
  argv and `HF_HUB_OFFLINE` and writes a model the way `hf` / `mlx_lm.convert` would. No real
  download was run: by policy, `.claude/settings.json` denies agents `make models-download` and
  `make models-convert` (the hook refused them during this session), so a real fetch is always a
  person's decision (BR-1). The real `hf` and `mlx_lm.convert` flags were checked with `--help`
  from `~/Models/.venvs/mtplx` before writing the templates.
- The PRD's `mlx-lm` venv does not exist on this Mac yet; until it does, a confirmed download
  ends as `acquire: failed` with the reason in `acquire-<role>.log` (covered by
  `test_us_2_4_default_commands_use_the_model_venv`).
- Downloads are background jobs because a multi-GB fetch outlives the gateway's 5 s worker
  timeout; `test_us_2_4_download_in_progress_and_shutdown` covers `in_progress` and the worker
  stopping a running job on shutdown.
- Fixed after independent review, each with a regression test: `confirm` is a strict JSON
  boolean (`"yes"` and `1` were coerced to true); the gateway accepts only
  `Content-Type: application/json`; an interrupted multi-shard download reads `missing` and resumes
  (`test_us_2_4_interrupted_multi_shard_download_is_resumed`); a conversion holds back every load
  and no server starts from a directory a job is writing; a failed shared download marks every
  role sharing the directory. Found before the review: jobs are keyed by target directory, so
  phi_detection and classification share one download
  (`test_us_2_4_roles_sharing_a_directory_share_one_download`).
- The gateway relays only the worker codes the desktop half acts on, and only with the status
  that code is answered with; the message is always the fixed one (`test_us_2_4_client_*`).
