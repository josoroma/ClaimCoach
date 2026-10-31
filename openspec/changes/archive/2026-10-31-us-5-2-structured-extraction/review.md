# Review: US-5.2

Change: us-5-2-structured-extraction
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | `Reading` failed as a whole on a `null` list, a malformed line, or a value of the wrong JSON type, so a real model reply (the prompt itself allows `null`) lost the whole page | `Reading` reads each list one item at a time (`null` or a non-list is empty, a bad item is dropped) and each value through `_scalar` (a boolean, object, or list is absent); `test_us_5_2_null_lists_and_bad_items_keep_the_rest` drives such a reply through the worker, gateway, and store |
| medium | Typed but unconfirmed values survived New case, Refresh, and a finished run, so case A's value could be confirmed into case B | The pane clears its edits on New case, Refresh, a finished or failed run, and whenever a result names another case; `values typed for one case never show in another`, `a finished run replaces anything typed before it` |
| medium | `keep_confirmed` re-applied line confirmations by position, so a re-run whose lines come from another source put a confirmed amount on another line | `CaseExtraction.itemized_by` records the source of the lines; line, adjustment, and remark confirmations are kept only when that source and the number of lines are unchanged, claim-level ones always; spec delta updated; `test_us_5_2_line_confirmations_stay_with_their_source` |
| medium | The relay ended at its deadline without a final event, leaving the pane on "Processing…" | Jobs stop at 60 min with `processing_timeout`; the relay outlives that by 5 min and then publishes `failed` with `processing_timeout`; `test_us_5_2_jobs_stop_at_their_deadline`, `test_us_5_2_relay_stops_at_its_deadline` (now asserts the event) |
| low | JSON `true` became `1` before validation | `_scalar` reads booleans as absent; covered through the whole pipeline by the high finding's test |
| low | Every `POST /process` started a relay, so events were broadcast twice | One relay per job (`_RELAYS` keyed by job ID); `test_us_5_2_one_relay_per_job` |
| low | `save_extraction` and `confirm_field` read and wrote without excluding each other | A per-case lock in `CaseService` around both read-merge-write sequences; `test_us_5_2_save_and_confirm_hold_the_case_lock` |
| low | CMYK JPEGs failed silently; page rendering had no pixel cap | Images are converted to RGB and halved until they fit 2000 px; pages render at the dpi that keeps the longest side within 2000 px; undecodable documents are listed in `unread_sources` and the pane names them; `test_us_5_2_cmyk_and_oversized_images_are_normalized`, `documents that could not be read are named in the status` |
| low | `confirm_field` on a purged case answered `invalid_request` | It checks the case is open first; `test_us_5_2_confirming_on_a_closed_case_says_closed` |
| low | `case-confirm` spliced `VALUE` into shell quotes | `FIELD` and `VALUE` reach the recipe only through the environment (`export FIELD VALUE`) |
| info | Tasks unchecked, evidence missing | Evidence recorded in `evidence/US-5.2/`; tasks checked before archive |

Also checked by the reviewer and found sound: `ctx.onEvent` is the tracked form of the same gateway stream the story's `host.onEvent` names (Hermes SDK `plugin.ts`, desktop-plugin-sdk.md), so US-3.3's no-`host` rule holds.

A regression found while fixing: the relay first imported the job module, which would have loaded PyMuPDF into the gateway. `JOB_DEADLINE` now lives in `cases/extraction.py`; `test_us_5_2_gateway_never_loads_pymupdf` keeps it so.

## Re-verification

`make verify` → exit 0 on the fixed tree (2026-10-31): ruff, ruff format, biome, mypy --strict ×2,
tsc --checkJs; 976 offline pytest tests passed at 100% line and branch coverage of `plugin/`; node
tests at 100% line, branch, and function coverage of `plugin.js`; evidence-check `ok` for every
report through US-5.2 (OhMyOrch accepted each); 2 gate self-tests passed. Evidence recorded by the
independent `story-tester` after the fixes, including an operator run of the `make case-*` targets
against a scratch worker (no Keychain item, no real patient data).
