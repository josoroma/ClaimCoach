# Review: US-3.6

Change: us-3-6-prompt-data-isolation
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-3-1-phi-detector
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | "Registered template only" and "only `BuiltPrompt` reaches the model" were conventions: a runtime `PromptTemplate` with document text in `system`, or a hand-built `BuiltPrompt`, type-checked | `build_prompt` refuses a template that is not the registered object of its name; `BuiltPrompt` validates that the system message is the registered system text plus the data rule and the user message is the instructions followed only by data blocks; `test_us_3_6_unregistered_templates_are_refused`, `test_us_3_6_hand_built_prompts_cannot_move_text_out_of_the_data` |
| low | `PIPELINE_MODULES` was a hand-kept list; a new prompt module could be missed | The test imports every `claimcoach` module with `pkgutil.walk_packages`; `test_us_3_6_pipeline_templates_are_discovered` |

## Re-verification

`make check` → exit 0 (710 pytest + 27 node tests, 100% line and branch coverage).
`make evidence STORY=US-3.6` → 9 passed. 

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
