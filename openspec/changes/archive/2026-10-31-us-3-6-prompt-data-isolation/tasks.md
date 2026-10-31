# Tasks

## 1. Builder

- [x] 1.1 Add `claimcoach/prompts/builder.py` (`PromptTemplate`, `DataItem`, `PromptParts`, `ChatMessage`, `BuiltPrompt`, `define_template`, `registered_templates`, `build_prompt`); verify `test_us_3_6_prompts_place_text_in_data_section`
- [x] 1.2 Random boundary redrawn on collision; verify `test_us_3_6_boundary_never_occurs_in_the_data`, `test_us_3_6_boundary_is_random_per_prompt`
- [x] 1.3 Template registry and validation; verify `test_us_3_6_templates_are_unique_and_validated`

## 2. Evidence

- [x] 2.1 Record `evidence/US-3.6/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
