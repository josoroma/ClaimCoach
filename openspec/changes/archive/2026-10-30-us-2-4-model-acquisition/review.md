# Review: US-2.4

Change: us-2-4-model-acquisition
Reviewer: independent general-purpose agent following `.claude/agents/story-reviewer.md` (read-only, given the changed files, not the implementer's reasoning), 2026-10-30
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | "Present" accepted config plus any one shard: a running or interrupted download read `present`, was served, and was never resumed | Every indexed shard required; no server starts from a directory a job is writing; `test_us_2_4_interrupted_multi_shard_download_is_resumed`, `test_us_2_4_no_server_starts_from_a_directory_being_written` |
| low | `confirm: bool` coerced `"yes"`/`1` to true; a test passed only because of an extra field | `StrictBool`; the cases are split (`"yes"`, `1`, extra field); `test_us_2_4_missing_confirmation_flag[6]` |
| low | Gateway parsed any content type, dropping the JSON check against cross-site POSTs | Only `application/json` accepted; `test_us_2_4_gateway_accepts_only_json_bodies[3]` |
| low | A failed shared download marked only the asking role | Every role sharing the directory; `test_us_2_4_failed_shared_download_marks_every_sharing_role` |
| medium | (Implementer, before review) Jobs keyed by role: phi_detection and classification could run two downloads into one directory | Jobs keyed by target directory; `test_us_2_4_roles_sharing_a_directory_share_one_download` |
| low | (Implementer, testing) `model_unavailable` (503) was not relayed by the gateway | Relay when status and code match; a 500 claiming `model_busy` is still `worker_error`; `test_us_2_4_client_*` |
| — | Decline path, offline conversion, fixed messages, 0600 logs | No issues found |

## Re-verification

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 260 pytest +
12 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all nine
stories, 2 gate self-tests). `pytest -m hermes` → 4 passed (the gateway, with the model routes,
loads in Hermes' Python 3.11). Live worker cycle with `make models-load` / `make worker-stop` →
no model server left behind.
