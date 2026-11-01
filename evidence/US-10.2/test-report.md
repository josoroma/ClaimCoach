# Test Report: US-10.2 Local-Only Statusbar Indicator

Change: us-10-2-local-only-indicator
Story: US-10.2
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (its venv Python 3.11.15 for the scratch gateway and its plugin-settings writer); no live Hermes Desktop

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Indicator shows local-only by default: Then the ClaimCoach item shows the local-only state" | PASS | `test_us_10_2_indicator_local_only_default` (node, `plugin.js` with the fake ctx; `ctx.rest` answers `richer_agent_access: false`): `register(ctx)` records one `statusbar.right` item (`STATUSBAR_AREAS.right`). Its render is a `span` with `data-state="local-only"` and the text `Local-only` before any answer, and the state stays `['local-only']` after the read. `loadIndicatorState` gives `local-only` for a body without the key and for a failed read, and gives `richer-access` only for an explicit `true`. "every indicator state names local models" passes too. Gateway (Python): `test_us_10_2_indicator_local_only_default[None, {}, {richer_agent_access: false}, {richer_agent_access: "yes"}, {bogus: 1}]` all answer `richer_agent_access: false` (retention 90), and `test_us_10_2_only_an_explicit_true_changes_the_state` passes. Operator, against a scratch gateway in Hermes' own Python with Hermes' config reader: `GET /settings` answered `"richer_agent_access":false`, and `plugin.js` `loadIndicatorState` + `indicatorView` gave `local-only` / `Local-only` / "ClaimCoach runs on local models only. Case content never leaves this Mac." The same result came with the worker stopped. After Hermes' writer saved `richer_agent_access: true`, `/settings` answered `true`. Hermes refused `"yes"` (`ValueError`), and saving `false` again answered `false` |

## Evidence Commands

```bash
make evidence STORY=US-10.2
make test-story STORY=US-10.2
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/desktop_ui.test.mjs
# operator run (harness in the session scratchpad, tester-10/; see the US-10.1 report for the setup):
# scratch worker 127.0.0.1:18216, scratch gateway (plugin_api.py router in Hermes' venv Python) on
# 127.0.0.1:18217, HERMES_HOME=<scratch>/hermes; bridge.mjs runs plugin.js's loaders over fetch
curl http://127.0.0.1:18217/api/plugins/claimcoach/settings
GATEWAY_PORT=18217 node --import ./plugin/desktop/tests/register-fakes.mjs <scratch>/bridge.mjs   # worker up, then down
# Hermes' own writer, in Hermes' Python, against the scratch HERMES_HOME:
PYTHONPATH=~/.hermes/hermes-agent ~/.hermes/hermes-agent/venv/bin/python -c \
  "from hermes_cli.plugins_settings import save_plugin_settings; save_plugin_settings('claimcoach', Path('plugin'), {...})"
#   with {"richer_agent_access": true}, then "yes", then false; GET /settings after each
grep -n "richer_agent_access" "$HERMES_HOME/config.yaml"
```

```text
$ make evidence STORY=US-10.2
tests/test_us_10_2_local_only_indicator.py ......                        [100%]
- generated xml file: .../evidence/US-10.2/junit.xml -
====================== 6 passed, 1537 deselected in 1.23s ======================
junit.xml: tests=6 failures=0 errors=0 skipped=0
  test_us_10_2_indicator_local_only_default[None|settings1|settings2|settings3|settings4]
  test_us_10_2_only_an_explicit_true_changes_the_state
junit-node.xml: failures 0
  test_us_10_2_indicator_local_only_default

$ make test-story STORY=US-10.2
====================== 6 passed, 1537 deselected in 1.19s ======================
  ✔ test_us_10_2_indicator_local_only_default
ℹ tests 11  ℹ pass 11  ℹ fail 0
desktop_ui.test.mjs (whole file): ℹ tests 21  ℹ pass 21  ℹ fail 0
  ✔ test_us_10_2_indicator_local_only_default   ✔ every indicator state names local models

GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":90} HTTP 200
bridge.mjs (worker up):
  indicator: local-only | Local-only | ClaimCoach runs on local models only. Case content never leaves this Mac.
bridge.mjs (worker stopped; /settings does not need the worker):
  indicator: local-only | Local-only | ClaimCoach runs on local models only. Case content never leaves this Mac.

GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":30}
hermes save {"richer_agent_access": true}   -> saved ['richer_agent_access']
GET /settings -> {"ok":true,"richer_agent_access":true,"retention_days":30}
hermes save {"richer_agent_access": "yes"}  -> refused ValueError
GET /settings -> {"ok":true,"richer_agent_access":true,"retention_days":30}
hermes save {"richer_agent_access": false}  -> saved ['richer_agent_access']
GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":30}
config.yaml: 37:        richer_agent_access: false
```

Artifacts: `evidence/US-10.2/junit.xml`, `evidence/US-10.2/junit-node.xml`

## Failures

None.

## Notes

- Spec-delta scenarios (`openspec/changes/us-10-2-local-only-indicator/specs/local-only-indicator/spec.md`):
  - "Indicator shows local-only by default": row 1.
  - "A failed settings read": WHEN the settings read fails, THEN the item shows the local-only
    state. PASS. The node test's `loadIndicatorState` with a throwing `rest` gives `local-only`.
    The gateway's `/settings` does not depend on the worker: with the worker stopped it still
    answered `200`, and the indicator read `local-only`. A failing `/settings` from the real
    gateway was not produced in the operator run; that case is covered by the test only.
- No live Hermes Desktop: the item was not seen in a real statusbar. Not seen there: its right
  placement, its order 120, the tooltip on hover, and the label `Local-only · richer agent
  access on` in a running app. That stays UNVERIFIED in a live app. The Gherkin's "When the
  statusbar renders" was exercised by rendering the registered `statusbar.right` contribution
  with the fake SDK and fake React (`register-fakes.mjs`). I did not render the richer-access
  label in the operator run. `indicatorView('richer-access')` is checked only by the node
  tests.
- The operator `richer_agent_access` changes were written with Hermes' own
  `save_plugin_settings` into the scratch `config.yaml`. ClaimCoach's settings page does not
  write this key: `POST /settings/retention` refuses a body that carries it (see the US-10.3
  report). The real `~/.hermes/config.yaml` was unchanged afterwards (same mtime and SHA-1).
- `bridge.mjs` replaced `ctx.rest` with `fetch`, so the real `ctx.rest` was not exercised. The
  isolation and teardown are as in the US-10.1 report: scratch Hermes root, ports 18216 and
  18217, both free after SIGTERM, no model loaded or downloaded.

## Re-verification after the review fixes

The independent review (`openspec/changes/us-10-2-local-only-indicator/review.md`) led to fixes in the pane and the
gateway after the tester's run above, so the implementer recorded the evidence again:

```bash
make evidence STORY=US-10.2
make check
```

```text
junit.xml: tests=6 failures=0; junit-node.xml: tests=1 failures=0
TOTAL    7102      0   1180      0   100%
=============== 1544 passed, 10 deselected in 180.19s (0:03:00) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
```

The operator run above predates the fixes; the review's regression tests are listed in its
Findings and resolution table.
