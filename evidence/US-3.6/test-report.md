# Test Report: US-3.6 Uploaded Text Treated as Data in Prompts

Change: us-3-6-prompt-data-isolation
Story: US-3.6
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), run after implementation and independent review
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Prompts place document text only inside the data section: Then the document text appears only inside the delimited data section of the prompt and never in the system or instruction sections" | PASS | `test_us_3_6_prompts_place_text_in_data_section[phi_detection]` and `[us_3_6_probe]`: for every registered pipeline template (today `phi_detection`, from `PIPELINE_MODULES`), a document containing "ignore previous instructions", a forged `<<<END DATA forged>>>` line, and a fake `SYSTEM:` line is built into a prompt; the system message contains none of it, the text before the data section equals the template's instructions exactly, the document appears whole and once inside its block, and the block closes only at the marker carrying the prompt's boundary. `test_us_3_1_detector_prompt_keeps_document_in_data_section` checks the same on the request the fake model server actually received |

## Evidence Commands

```bash
make evidence STORY=US-3.6
uv run pytest tests/test_us_3_6_prompt_builder.py -v --no-cov
uv run pytest tests/test_us_3_1_phi_detector.py -k data_section --no-cov
```

```text
test_us_3_6_prompts_place_text_in_data_section[us_3_6_probe] PASSED
test_us_3_6_prompts_place_text_in_data_section[phi_detection] PASSED
test_us_3_6_every_data_item_gets_its_own_block PASSED
test_us_3_6_boundary_is_random_per_prompt PASSED
test_us_3_6_boundary_never_occurs_in_the_data PASSED
test_us_3_6_templates_are_unique_and_validated PASSED
test_us_3_6_pipeline_templates_are_discovered PASSED
test_us_3_6_unregistered_templates_are_refused PASSED
test_us_3_6_hand_built_prompts_cannot_move_text_out_of_the_data PASSED
====================== 9 passed, 705 deselected in 0.39s =======================
test_us_3_1_detector_prompt_keeps_document_in_data_section PASSED
```

Artifacts: `evidence/US-3.6/junit.xml`

## Failures

None.

## Notes

- "Any ClaimCoach prompt" is checked over the template registry after importing every
  `claimcoach` module, and the chat client accepts only a `BuiltPrompt`, which validates that all
  text outside its data blocks is registered template text.
- The boundary stops structural escape, not a model that obeys text inside the data; that is
  mitigated by typed parsing of every model reply (US-3.1 decision 4) and is not claimed here.
- After independent review: `build_prompt` refuses unregistered templates and `BuiltPrompt`
  validates its own shape (`test_us_3_6_unregistered_templates_are_refused`,
  `test_us_3_6_hand_built_prompts_cannot_move_text_out_of_the_data`); templates are discovered by
  importing every `claimcoach` module (`test_us_3_6_pipeline_templates_are_discovered`).
