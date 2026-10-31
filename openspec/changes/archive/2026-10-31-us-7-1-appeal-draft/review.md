# Review: US-7.1

Change: us-7-1-appeal-draft
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | `make check` failed on mypy errors in the US-7.3 test file sharing the tree | Fixed (`LOOPBACK` imported from `worker.config`, typed probe endpoint, renamed the upload body); `make check` green |
| medium | `--reasoning off` reached only new installs: an existing `models.yaml` copy kept the old `drafting` command, so every draft would end `drafting_failed` | `ensure_registry_file` migrates an unedited pre-US-7.1 `drafting` line once (temporary file, rename, mode kept); an edited command is left alone and the upgrade runbook says how to add the flag; design decision 9, a new spec requirement; `test_us_7_1_unedited_drafting_command_migrates` |
| low | `MAX_TOKENS` 4096 could not hold a 20000-character letter, and a cut-off reply was indistinguishable from an unusable one | Budget 8192 tokens; a reply stopped at `max_tokens` is logged by kind (no text); `test_us_7_1_prompt_carries_letter_facts` (8192), `test_us_7_1_a_cut_off_reply_is_named_in_the_log` |
| low | The job did not re-check that the case was still open, so a case closed after Draft appeal still loaded the 27B model | `Drafter._inputs` calls `check_draftable` first; `test_us_7_1_a_closed_case_never_loads_the_model` |
| low | Draft again stayed enabled with unsaved editor text, which the new draft then discarded | The button is disabled while the editor holds unsaved text; node `Draft again waits for unsaved editor text; a refused start follows no job` |
| low | A refused draft start left the pane following a job, so a later job's events on the case read as a draft | `settle` stops following when the answer is not a running job; same node test |
| low | The BR-5 assertion passed for the wrong reason (the other case was never extracted) | The other case is extracted and diagnosed before drafting; its claim number is still absent from the prompt |
| info | Tasks unchecked, evidence missing | Evidence recorded by the independent `story-tester`; tasks checked before archive |

Also checked by the reviewer and found sound: the strict `AppealDraft` with its `Literal` label; the registered `appeal_draft` template and data blocks; template choice; refusals before a job exists; the `runner` override and `drafting_failed` default; the job deadline against queue, startup, and draft timeouts; the `case_items` migration; the gateway envelope and relayed codes; the `case-draft` target passing TEMPLATE through the environment; BR-1, BR-2, BR-4, BR-5, BR-6, BR-7, BR-10, BR-11, BR-12, BR-14.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-7 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1182 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 104 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-7.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
operator runs of `make case-draft` (with and without `TEMPLATE=`), `case-show`, `case-edit`, and
`case-export FORMAT=pdf|docx TO=…` against scratch workers with fake models and synthetic data;
the exported files were read back with pdftotext, pdfinfo, textutil, and unzip. The real-model
test `test_us_7_1_draft_real_model` ran Ternary-Bonsai-2-27B from `~/Models` through
`ModelManager` and passed (43 s), after `--reasoning off` was added (without it the same test
failed `drafting_failed`); no model server was left running.
