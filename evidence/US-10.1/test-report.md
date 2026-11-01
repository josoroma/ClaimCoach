# Test Report: US-10.1 Case Pane and Manager Dashboard Route

Change: us-10-1-case-list-and-dashboard
Story: US-10.1
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (its venv Python 3.11.15 for the scratch gateway); no live Hermes Desktop

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The case pane is registered: Then a pane contribution with the case list and case detail views is registered" | PASS | `test_us_10_1_case_pane_registered` (node, `plugin.js` loaded with the fake ctx from `fake_ctx.mjs`): `register(ctx)` records one pane `case-pane` with `{placement: 'right', width: '380px'}`. Its render is `ClaimCoachPane`, whose `aria-label` is `ClaimCoach` and whose two children are `CaseListView` (the case list) and `CasePane` (the case detail view), joined by one `link`. `test_us_10_1_listed_case_opens` passes too: selecting a row requests `/cases/<id>`, the detail view goes `ready` on that case, and the list reloads. The list's data, through the gateway (Python): `test_us_10_1_case_list_holds_no_content`, `_list_shows_steps_newest_first`, `_list_without_a_user_scope`, `_list_is_bounded`, and `_global_scope_has_no_cases` pass. Operator: `make case-list` on the scratch worker listed 4 cases newest first, with IDs, dates, outcome, counts, and step flags only. 0 matches for the synthetic payer, name, member ID, claim number, CARC, filename, or the word "denied". The audit stayed at 11 entries across the list, and `make case-show` then added `case_opened` (seq 12). `plugin.js`'s own `loadCaseList` and `describeCaseRow`, run against a scratch gateway in Hermes' Python, rendered rows such as `case_894443949da5ef82: opened 2026-11-01 · New · 0 document(s) · Overturned · closed` |
| 2 | "The dashboard route is registered: Then a route contribution for the manager dashboard is registered" | PASS | `test_us_10_1_dashboard_route_registered` (node, fake ctx): exactly one `routes` contribution, id `dashboard`, `data.path` equal to `DASHBOARD_PATH` (`/claimcoach/dashboard`), and its render is `DashboardPage`. The sidebar `nav` contribution has the same path |
| 3 | "Backend errors render as an error state: Then the pane shows an error state instead of throwing" | PASS | `test_us_10_1_backend_errors_render_error_state` (node): `ctx.rest` rejects with a `503 worker_unavailable` envelope. Rendering the list does not throw. The state goes `{state: 'unavailable'}` and renders a `role="alert"` with `CASE_LIST_UNAVAILABLE` and a **Retry** button, and the envelope's `secret text` is not shown. An `{ok: false}` body also reads as `unavailable`. Gateway half: `test_us_10_1_list_through_the_gateway_when_the_worker_is_down` (`503 worker_unavailable`). Operator: with the scratch worker stopped, the scratch gateway answered `GET /cases` with `503 {"ok":false,"error":{"code":"worker_unavailable",...}}`. `plugin.js` `loadCaseList` turned that into `{"state":"unavailable"}` -> "Cases could not be loaded. Check that the ClaimCoach backend and worker are running." |

## Evidence Commands

```bash
make evidence STORY=US-10.1
make test-story STORY=US-10.1
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/desktop_ui.test.mjs
npm exec --no -- tsc --noEmit -p tsconfig.json
# operator run, scratch harness in the session scratchpad (tester-10/), synthetic data only:
#   serve_ui_worker.py: real create_app, tests/fakes make_service (FakeModelServer,
#     InMemoryKeyProvider), a status-only ModelManager over an empty scratch MODELS_HOME,
#     configure_logging to a scratch worker.log; seeds two closed synthetic cases
#   serve_gateway.py: plugin/dashboard/plugin_api.py's router in Hermes' venv Python, mounted at
#     /api/plugins/claimcoach on 127.0.0.1:18217; get_worker_client pointed at 18216
#   bridge.mjs: plugin.js's loaders (loadCaseList, describeCaseRow, ...) over fetch to that gateway
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18216
make case-list
make case-new; make case-paste CASE=<A> FILE=<scratch>/data/letter.txt
make case-new; make case-outcome CASE=<B> OUTCOME=upheld
curl ... "http://127.0.0.1:18216/corpus/audit?profile=default"     # before and after the list
make case-list; grep -c <each canary> list.json
make case-list PROFILE=biller-b
make case-show CASE=<A>; curl ... /corpus/audit
curl http://127.0.0.1:18217/api/plugins/claimcoach/cases
GATEWAY_PORT=18217 node --import ./plugin/desktop/tests/register-fakes.mjs <scratch>/bridge.mjs
kill -TERM <worker pid>                                              # worker down
curl http://127.0.0.1:18217/api/plugins/claimcoach/cases; make case-list
GATEWAY_PORT=18217 node --import ./plugin/desktop/tests/register-fakes.mjs <scratch>/bridge.mjs
kill -TERM <worker pid> <gateway pid>; lsof -nP -iTCP:18216 -sTCP:LISTEN; lsof -nP -iTCP:18217 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-10.1
tests/test_us_10_1_case_list.py ......                                   [100%]
- generated xml file: .../evidence/US-10.1/junit.xml -
====================== 6 passed, 1537 deselected in 2.03s ======================
junit.xml: tests=6 failures=0 errors=0 skipped=0
  test_us_10_1_case_list_holds_no_content, _list_shows_steps_newest_first,
  _list_without_a_user_scope, _list_is_bounded, _global_scope_has_no_cases,
  _list_through_the_gateway_when_the_worker_is_down
junit-node.xml: failures 0
  test_us_10_1_case_pane_registered, test_us_10_1_listed_case_opens,
  test_us_10_1_dashboard_route_registered, test_us_10_1_backend_errors_render_error_state

$ make test-story STORY=US-10.1
====================== 6 passed, 1537 deselected in 1.38s ======================
  ✔ test_us_10_1_case_pane_registered
  ✔ test_us_10_1_listed_case_opens
  ✔ test_us_10_1_dashboard_route_registered
  ✔ test_us_10_1_backend_errors_render_error_state
ℹ tests 14  ℹ pass 14  ℹ fail 0

desktop_ui.test.mjs (whole file): ℹ tests 21  ℹ suites 5  ℹ pass 21  ℹ fail 0
tsc --noEmit (checkJs): exit 0; plugin.js has 117 jsx( and 20 jsxs( calls and no JSX syntax

$ make case-list            (two seeded cases, before any make-created case)
True [('case_000000000000a010', '2026-10-22T02:30:07.473147Z', None),
      ('case_000000000000a045', '2026-09-17T02:30:07.472421Z', None)]
audit: 11 entries; last: 11 case_closed case_546260e5a4f005fc
$ make case-list            exit=0
    "case_id": "case_546260e5a4f005fc", "opened_at": "2026-11-01T02:30:25.154204Z",
    "closed_at": "2026-11-01T02:30:25.320177Z", "purged_at": null, "outcome": "upheld",
    "documents": 0, "calls": 0, "extracted": false, "diagnosed": false, "drafted": false
    "case_id": "case_3c23cad1fec71cf1", ... "closed_at": null, "outcome": null, "documents": 1, ...
    "case_id": "case_000000000000a010", ...   "case_id": "case_000000000000a045", ...
audit: 11 entries; last: 11 case_closed case_546260e5a4f005fc      (listing is not audited)
grep ACME | Jane | SYN-0001 | SYNTH-CLAIM-77 | CO-197 | letter.txt | denied | SYNTH-45: 0 each
$ make case-list PROFILE=biller-b
{"ok":true,"cases":[]}
$ make case-show CASE=case_3c23cad1fec71cf1
audit: 12 entries; last: 12 case_opened case_3c23cad1fec71cf1

GET /api/plugins/claimcoach/cases (scratch gateway) -> HTTP 200 True
  [('case_546260e5a4f005fc', 0, 'upheld'), ('case_3c23cad1fec71cf1', 1, None), ('case_000000000000a010', 0, None), ...]
bridge.mjs (plugin.js loaders, worker up):
  case row: case_894443949da5ef82: opened 2026-11-01 · New · 0 document(s) · Overturned · closed
  case row: case_000000000000a010: opened 2025-09-27 · New · 0 document(s) · closed
  case row: case_000000000000a045: opened 2025-09-27 · New · 0 document(s) · content purged

worker stopped (18216 listeners: 0)
GET /cases -> {"ok":false,"error":{"code":"worker_unavailable","message":"The ClaimCoach worker is not running."}} HTTP 503
bridge.mjs: case list: {"state":"unavailable"} -> Cases could not be loaded. Check that the ClaimCoach backend and worker are running.
$ make case-list
curl: (7) Failed to connect to 127.0.0.1 port 18216 after 0 ms: Couldn't connect to server
Expecting value: line 1 column 1 (char 0)
make: *** [case-list] Error 1                                       exit=2

after SIGTERM: ports 18216 and 18217 free; no harness process left
~/.hermes/config.yaml: same mtime (1792951429) and sha1 (50907efc...) before and after
```

Artifacts: `evidence/US-10.1/junit.xml`, `evidence/US-10.1/junit-node.xml`

## Failures

None.

## Notes

- Spec-delta scenarios (`openspec/changes/us-10-1-case-list-and-dashboard/specs/desktop-case-pane/spec.md`):
  - "The case pane is registered", "The dashboard route is registered", and "Backend errors
    render as an error state" are rows 1 to 3.
  - "A listed case opens in the detail view": PASS, but only under the fakes.
    `test_us_10_1_listed_case_opens` covers it. The test "the detail view reloads the list when
    it moves to another case" passes too. Operator: `make case-show` on a listed ID opened it and
    was audited `case_opened`, as the runbook says.
  - "The list of cases": each case shows its ID, dates, and steps, and no document text, payer,
    or claim number. PASS. `test_us_10_1_case_list_holds_no_content` checks this, and so does
    the operator canary grep above. The list is capped at 200 (`test_us_10_1_list_is_bounded`,
    tests only). It is not audited (audit count unchanged). A profile with no user scope gets an
    empty list (`make case-list PROFILE=biller-b` before that profile had a case).
- No live Hermes Desktop: the pane rendered in the right-hand panel, the sidebar entry, the
  dashboard page at `/claimcoach/dashboard`, and clicking a row in a real host were not seen.
  The node tests exercise every Gherkin scenario through `plugin.js` with a fake ctx, the fake
  SDK, and a fake React (`register-fakes.mjs`), which is what the Gherkin's "Given plugin.js
  loaded with a fake ctx" asks for. The live rendering stays UNVERIFIED. That includes runbook
  step 1's "Cases" list in the pane, its "Retry" with the worker stopped, and runbook step 3.
- `bridge.mjs` replaced Hermes' `ctx.rest` with `fetch`, throwing `"<status>: <body>"` on a
  non-2xx answer, the same shape the node tests use for a rejection. How the real `ctx.rest`
  rejects was not observed.
- How the operator run was isolated: the harness scripts sit in this tester's scratchpad
  (`.../scratchpad/tester-10/`), not in the repo. `serve_ui_worker.py` refuses any
  `HERMES_HOME` or `MODELS_HOME` outside that folder. It used an `InMemoryKeyProvider` (no
  Keychain item) and an in-process `FakeModelServer`. It served on 127.0.0.1:18216, with the
  scratch gateway on 18217. The gateway's `get_worker_client` was overridden, because the real
  one always targets 18200. All data was synthetic. Three short runs used fresh scratch Hermes
  roots, because the in-memory store key does not survive a restart. No model was loaded or
  downloaded. The real `~/.hermes/config.yaml` was unchanged afterwards (same mtime and SHA-1),
  and both ports were free after SIGTERM.
- Seeded cases (created with `tests/fakes` `add_case_document`) show `documents: 0`. The count
  covers case items of kind `source`, which the real intake writes (the pasted case shows `1`).
  The helper writes a corpus document only. This is a harness artifact, not a defect.
- With the worker stopped, `make case-list` prints curl's error and then the `json.tool` line
  `Expecting value: line 1 column 1 (char 0)`, and exits 2. This is cosmetic, and the same as
  the other `case-*` targets.

## Re-verification after the review fixes

The independent review (`openspec/changes/us-10-1-case-list-and-dashboard/review.md`) led to fixes in the pane and the
gateway after the tester's run above, so the implementer recorded the evidence again:

```bash
make evidence STORY=US-10.1
make check
```

```text
junit.xml: tests=6 failures=0; junit-node.xml: tests=4 failures=0
TOTAL    7102      0   1180      0   100%
=============== 1544 passed, 10 deselected in 180.19s (0:03:00) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
```

The operator run above predates the fixes; the review's regression tests are listed in its
Findings and resolution table.
