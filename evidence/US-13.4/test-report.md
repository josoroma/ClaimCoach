# Test Report: US-13.4 App Flow Diagrams for Stakeholders and Users

Change: us-13-4-flow-diagrams
Story: US-13.4
Verdict: pass
Coverage: 8/8 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer re-run after US-13.7 and US-13.8 amended the last two scenarios
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The stakeholder diagram shows the PHI boundary: Then it shows the Mac boundary with the pane, plugin_api, the worker, the local model servers, and the two corpus scopes inside it" | PASS | `test_us_13_4_stakeholder_diagram_shows_boundary`: the pane, `plugin_api.py`, Worker, Local models ("7 roles · loopback", the registry's count), PDF or DOCX, Global corpus, User corpus, and Agent tools are inside the `zone-accent` (Mac) rect; the chat agent is outside it, in the `zone` band; the two callouts are outside the Mac |
| 2 | "The stakeholder diagram shows the PHI boundary: And the Hermes chat agent receives only case IDs, codes, payer names, and redacted summaries" | PASS | Same test: the agent's sublabel is "IDs · codes · payer names"; every arrow is read node to node, and the only one into the agent is `arrow-accent nophi` from Agent tools, labeled REDACTED ONLY between the two; worker→User corpus is solid (case content, SEALED), worker→Global corpus and worker→Agent tools are `nophi`. Probes making the user-corpus arrow dashed or dropping the agent's sublabel fail it |
| 3 | "The user diagram follows a case from upload to outcome: Then it shows upload or paste, extraction and confirmation, diagnosis, drafting, edit and export, and the outcome, with the model each step uses" | PASS | `test_us_13_4_user_diagram_follows_case`: each step's tag is "STEP n" (" · YOU" on 3, 6, 7); Extract, Diagnose, and Draft name exactly their roles' models from `models.default.yaml` and the other steps name none; an arrow joins each step to the next, the payer call feeds Add documents, and the outcome feeds the manager dashboard (`nophi`). Probes reversing the step 1→2 arrow or adding the drafting model to Extract fail it |
| 4 | "The developer diagram follows one extraction: Then it shows one extraction from the pane through plugin_api and the worker to the model server and the user corpus, each message between the lifelines that exchange it, in order" | PASS | `test_us_13_4_request_diagram_follows_request`: each message label is paired with the arrow 8px under it, and the list of (label, from, to, kind) top to bottom equals the expected twelve, from `POST /cases/{case_id}/process` (pane → plugin_api, call) to `Case` (plugin_api → pane, return). Routes are read from the gateway and worker routers, the event from `CaseProgressEvent.EVENT`, `JobStarted`'s fields from the model, ports from `models.default.yaml` and `WorkerConfig`; the token, memory-guard, and proxy notes sit under their messages. Probes drawing JobStarted from the worker to the pane, extract from the pane, the sealed write from the pane, or dropping the token note fail it |
| 5 | "The developer diagram follows one extraction: And only the gateway's polling for progress events repeats, until the job ends" | PASS | Same test: the messages whose arrows lie within the `LOOP` frame's height are exactly `GET /jobs/{job_id}/events`, `events after n`, and `plugin.claimcoach.case.progress`, and the frame holds the `LOOP` tab and the `[until the job ends]` guard. A probe stretching the frame over the model call fails it ("only the polling repeats") |
| 6 | "The diagrams are self-contained and shown in the guide: Then it is a valid SVG with a title and no script, external reference, or embedded image" | PASS | `test_us_13_4_diagrams_self_contained` runs the shared `self_contained_svg` (US-13.1) on every `docs/assets/*.svg`, which are exactly the three flow diagrams |
| 7 | "The diagrams are self-contained and shown in the guide: And it switches to the theme's light colors on a page that prefers a light color scheme" | PASS | Same test: each style has the `prefers-color-scheme: light` query; US-13.8's `test_us_13_8_light_handled` checks it sets the theme's light values. Seen in the browser pane on a dark and a light page |
| 8 | "The diagrams are self-contained and shown in the guide: And README-DEV.md shows every diagram" | PASS | Same test: each file is an image (`![…](docs/assets/<name>)`) under App flows, outside HTML comments |

## Evidence Commands

```bash
make evidence STORY=US-13.4
uv run python <scratchpad>/mut14/probe.py <scratchpad>/mut14   # mutations of the redrawn diagrams
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
====================== 4 passed, 1887 deselected in 1.42s ======================
caught jobstarted_skips_gateway - AssertionError: (assert)
caught extract_from_pane - AssertionError: (assert)
caught pane_writes_corpus - AssertionError: (assert)
caught model_call_in_loop - AssertionError: only the polling repeats
caught token_note_dropped - KeyError: 'per-launch bearer token'
caught user_arrow_reversed - AssertionError: no arrow from Add documents to Extract
caught drafting_on_extract - AssertionError: Extract names the models of its own roles only
caught user_corpus_dashed - AssertionError: case content stays on the Mac; only redacted results reach the chat agent
caught agent_label_dropped - AssertionError: what it may see
All checks passed!
TOTAL    8551      0   1414      0   100%
=============== 1877 passed, 14 deselected in 238.26s (0:03:58) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.4/junit.xml`

## Failures

None.

## Notes

- Re-run 2026-11-01 after US-13.6 to US-13.8 redrew the diagrams. US-13.7's `flow-diagrams` delta replaced "The developer diagram follows one request" with "The developer diagram follows one extraction", and "The diagrams are self-contained and readable in light and dark themes" with "The diagrams are self-contained and shown in the guide" (SPECS.md matches). `test_us_13_4_diagram_check_refuses_light_only` was removed with the background rule it tested; the four scenario tests kept their names.
- How GitHub renders the SVGs was not seen; both themes were checked in the browser pane with color-scheme emulation.
- First review's fixes (see the archived review.md) still hold: step 3 confirms only unreadable fields, the agent sees payer names, encryption is per value, and Diagnose names no retrieval.
