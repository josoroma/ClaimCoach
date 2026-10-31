# Review: US-3.1

Change: us-3-1-phi-detector
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-3-6-prompt-data-isolation. Live operator run by an independent `story-tester` agent.
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | Catastrophic backtracking: adjacent unbounded whitespace quantifiers between labels and values took 29.8 s on "Member" + 400 spaces, on the worker's event loop | Every repeat bounded (`{0,4}`); regex work moved to `asyncio.to_thread`; `test_us_3_1_validators_resist_backtracking` (36 cases, 10 000 characters, < 0.5 s); live 5 000-space document 0.08 s |
| high | Model values matched only verbatim: a one-line address against a two-line block (or doubled spaces) was silently dropped | Words-in-order match across up to 8 non-word characters; unlocatable values contribute their distinctive words; dropped-value count logged; `test_us_3_1_model_values_match_across_layout_changes`, `test_us_3_1_unlocatable_values_fall_back_to_their_words` |
| high | Months case-sensitive: `DOB: JAN 02 1960` passed | `_DATE` case-insensitive, ordinals, `DD-MON-YYYY`; validator cases added |
| medium | 28 common label and value variants unrecognised (`ID:`, `Mbr ID`, `Pat Acct`, `PCN`, `MR#`, `MBI`, `HICN`, `(MM/DD/YYYY)`, spaced IDs, masked/dotted SSN, 10-digit phone, extensions) | Labels and shapes added; 30 new `test_us_3_1_validator_matches` cases; negative cases (`Identified`, codes, unlabeled dates) still pass |
| medium | Two-letter surnames (Li, Ng) never propagated | Redacted after a title or before a comma and another name word; `test_us_3_1_two_letter_surnames_are_redacted_in_name_context`, `test_us_3_1_names_of_only_short_words_use_the_title_context` |
| medium | Tests passed by construction (fixtures used only formats the validators knew; fake model echoed exact substrings) | Adversarial `caps_eob` fixture kind (all caps, 40-space table, two-line address, two-letter surname, upper-case DOB); fake model answers with a model's spelling (`PhiDocument["model"]`); whole-word leak check (`leaked_strings`) |
| low | No overall deadline across chunks (≈ 68 min holding the model) | `total_timeout` 300 s → `redaction_failed`; `test_us_3_1_detection_has_a_total_deadline` |
| low | `test_us_3_1_random_boundary_survives_any_document` passed for the wrong reason | Removed; `test_us_3_6_boundary_never_occurs_in_the_data` covers it |
| low | `make redact` crashed with `KeyError` on an error envelope and put the file path in argv | File read on stdin; prints `error: <code>` and exits 1 |
| low (from US-3.2 review) | Snake_case JSON keys (`member_id`, `date_of_birth`) not matched as labels | Labels accept underscores and quotes; validator cases added |
| info (tester) | Real Qwen3-8B run skipped: weights not under `~/Models` | Recorded UNVERIFIED in the evidence; no download made (BR-1) |

## Re-verification

`make check` → exit 0 (710 pytest + 27 node tests, 100% line and branch coverage).
`make evidence STORY=US-3.1` → 129 passed. Live: scratch worker with the fake PHI model, `make redact`
→ all seven categories, no seeded string; `make stop` → no port left listening.

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
