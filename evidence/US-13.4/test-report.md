# Test Report: US-13.4 App Flow Diagrams for Stakeholders and Users

Change: us-13-4-flow-diagrams
Story: US-13.4
Verdict: pass
Coverage: 8/8 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The stakeholder diagram shows the PHI boundary: Then it shows the Mac boundary with the pane, plugin_api, the worker, the local model servers, and the two corpus scopes inside it" | PASS | `test_us_13_4_stakeholder_diagram_shows_boundary`: the pane, `plugin_api.py`, Worker, Local models, Global corpus, User corpus, and Agent tools are drawn inside the `zone` rect; the chat agent, payers, and model weights outside it. Viewed in the browser pane |
| 2 | "The stakeholder diagram shows the PHI boundary: And the Hermes chat agent receives only case IDs, codes, payer names, and redacted summaries" | PASS | Same test: every arrow ending at the chat agent's box has class `leave` (no PHI) and starts in the Agent tools box, and its two labels sit between them. A probe adding a `phi` arrow from the worker to the agent fails it |
| 3 | "The user diagram follows a case from upload to outcome: Then it shows upload or paste, extraction and confirmation, diagnosis, drafting, edit and export, and the outcome, with the model each step uses" | PASS | `test_us_13_4_user_diagram_follows_case`: each step's title and number 1–7 are inside the same card; Extract, Diagnose, and Draft cards name their roles' models from `models.yaml`; every model named anywhere is a `models.yaml` folder. Probes swapping titles, adding `Llama-70B`, or putting Bonsai on Extract each fail it |
| 4 | "The developer diagram follows one request: Then it shows one extraction from the pane through plugin_api and the worker to the model server and the user corpus, in order" | PASS | `test_us_13_4_request_diagram_follows_request`: the gateway and worker routes it draws are read from their routers, the event from `CaseProgressEvent.EVENT`, the ports from `models.yaml` and `WorkerConfig`; the steps are drawn top to bottom in order. Renaming `/jobs/{job_id}/events` fails it |
| 5 | "The developer diagram follows one request: And the job's progress events repeat while the job runs" | PASS | Same test: the events poll, model start, sealed write, and `plugin.claimcoach.case.progress` are inside the `loop` box; `JobStarted` and the final `GET /cases/{case_id}` are outside it |
| 6 | "The diagrams are self-contained and readable in light and dark themes: Then it is a valid SVG with a title and no script, external reference, or embedded image" | PASS | `test_us_13_4_diagrams_self_contained` runs the shared `self_contained_svg` (US-13.1) on every `docs/assets/*.svg` |
| 7 | "The diagrams are self-contained and readable in light and dark themes: And it draws its own background and switches its colors for a dark color scheme" | PASS | Same test: the `bg` rect is drawn first over the whole viewBox, has a fill in the light and dark rules, and every styled class has a dark rule (`test_us_13_4_diagram_check_refuses_light_only` shows a class without one fails). The dark rules were applied in the browser pane and the request diagram read correctly |
| 8 | "The diagrams are self-contained and readable in light and dark themes: And README-DEV.md shows every diagram" | PASS | Same test: each file is an image (`![…](docs/assets/<name>)`) under App flows, outside HTML comments |

## Evidence Commands

```bash
make evidence STORY=US-13.4
uv run python <scratchpad>/mut13/probe.py <scratchpad>/mut13   # the reviewer's mutations
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
====================== 5 passed, 1821 deselected in 2.05s ======================
caught phi_to_agent - only a no-PHI, boundary-crossing arrow reaches the chat agent
caught swap_titles - step Diagnose is not drawn
caught llama - Llama-70B?
caught bonsai_on_extract - Extract's card names the extraction model
caught event_outside_loop - plugin.claimcoach.case.progress repeats while the job runs
caught route_renamed - GET /jobs/{job_id}/events is not drawn
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 250.31s (0:04:10) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.4/junit.xml`

## Failures

None.

## Notes

- How GitHub renders the SVGs in its dark theme was not seen; the dark rules were checked by applying them in the browser pane.
- Review fixes (see review.md): step 3 now says only unreadable fields are confirmed, the request diagram draws the event relay as a loop during the job, the agent arrow names payer names, encryption is per value, and the Diagnose card names rule cards instead of retrieval.
