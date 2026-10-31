# Test Report: US-7.3 No Send or Submit Anywhere

Change: us-7-3-no-send-submit
Story: US-7.3
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "No contribution offers send or submit: Then none has a label or command that sends or submits to a payer" | PASS | Node: `test_us_7_3_no_send_contribution` loads `plugin.js` with a fake ctx and collects every registered contribution (at least 4) and the settings page. It walks each `render()` output and the case pane in six states (idle, busy, drafting, unavailable, a diagnosed case with a stale, edited draft and a saved export, and one with a written export), seeing at least 40 controls including `Export PDF` and `Draft again (replaces your edits)`. No label, title, placeholder, or command matches the send pattern (`send`, `submit`, `fax`, `e-mail`, `mailto`, `transmit`, `deliver`, `upload to`, `to the payer`, `portal`, `clearinghouse`, `file with`), there is no `<form>`, and no link leaves the app. The companion test "the check catches a send control" confirms the walk finds such controls when they exist, including inside nested elements, memo and forwardRef wrappers, function components, and `form`/`mailto`/`https` targets. `test_us_7_3_plugin_js_header_cites_br_4`. My own check: `grep -i -E "send\|submit\|fax\|e-?mail\|transmit\|deliver\|portal\|clearinghouse" plugin/desktop/plugin.js` matched only the header comment, which states the rule, and an internal parameter named `send` in `addDocument`. No `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `window.open`, `openExternal`, `mailto:`, or `http(s)://` appears in `plugin.js` |
| 2 | "No backend route transmits case content: Then no route sends case content to a non-loopback destination" | PASS | `test_us_7_3_no_transmitting_route`: the gateway's 15 routes and the worker's 24 routes (with every optional part mounted) equal the pinned tables. No path or endpoint name is send-like. The gateway reaches the worker at `http://127.0.0.1:`, and the only outbound route, `POST /models/download`, takes `{role, confirm}` only. `test_us_7_3_case_routes_reach_only_loopback` runs every case route end to end through the gateway and records every socket connect. `test_us_7_3_http_clients_only_in_loopback_modules` and `test_us_7_3_the_scan_catches_a_way_out[...]` (14 cases): no mail, FTP, or raw HTTP imports, and HTTP clients, processes, and sockets appear only in reviewed modules. `test_us_7_3_the_route_walk_sees_every_route_type`, `test_us_7_3_docstrings_cite_br_4[...]` (6 modules). My own route enumeration (`enum_routes.py`, which walks `routes.router` and `create_app(...)` with the model manager and corpus mounted) listed the same 15 gateway and 24 worker routes, and none was send-like. Operator: a scratch worker on 127.0.0.1:18216 ran a full case (new, paste, process, diagnose, draft, edit, confirm, export PDF and DOCX, show) under a `sys.addaudithook` socket-connect log. Every outgoing connect from the worker process went to `127.0.0.1` (4 distinct ports, the in-process fake model servers) |

## Evidence Commands

```bash
make evidence STORY=US-7.3
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_7_3 -v
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/appeal_draft.test.mjs
grep -n -i -E "send|submit|fax|e-?mail|transmit|deliver|portal|clearinghouse" plugin/desktop/plugin.js
grep -n -E "fetch\(|XMLHttpRequest|WebSocket|sendBeacon|window\.open|openExternal|mailto:|https?://" plugin/desktop/plugin.js
uv run python -W ignore <scratch>/enum_routes.py
# operator run on a fresh scratch worker (serve_draft_worker.py as in US-7.1, wrapped by
# audit_wrap.py, which logs every socket.connect/sendto of the worker process), WORKER_PORT=18216
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18216
make case-new; make case-paste CASE=case_8b945401fcf346ca FILE=<scratch>/era.835
make case-process ...; make case-diagnose ...; make case-draft ...; make case-edit ... FILE=<scratch>/edited.txt
make case-confirm ... FIELD=claim_id VALUE=CLAIM-77
make case-export ... FORMAT=pdf TO=<scratch>/out73; make case-export ... FORMAT=docx TO=<scratch>/out73; make case-show ...
sort <scratch>/connects.log | uniq -c
```

```text
tests/test_us_7_3_no_send_submit.py ..........................           [100%]
- generated xml file: .../evidence/US-7.3/junit.xml -
===================== 26 passed, 1165 deselected in 1.80s ======================
test_us_7_3_no_transmitting_route PASSED
test_us_7_3_the_route_walk_sees_every_route_type PASSED
test_us_7_3_case_routes_reach_only_loopback PASSED
test_us_7_3_http_clients_only_in_loopback_modules PASSED
test_us_7_3_the_scan_catches_a_way_out[...] PASSED (14 cases: smtplib, http.client, urllib.request,
  email.mime, httpx clients, asyncio/socket connections, subprocess curl, os.system lp, os.execvp
  osascript, importlib/__import__ smtplib)
test_us_7_3_the_scan_passes_plain_code PASSED
test_us_7_3_docstrings_cite_br_4[...] PASSED (6 modules)
test_us_7_3_plugin_js_header_cites_br_4 PASSED

junit-node.xml: 1 US-7.3 case, fail 0
  test_us_7_3_no_send_contribution
appeal_draft.test.mjs (whole file, includes "the check catches a send control"):
ℹ tests 17  ℹ pass 17  ℹ fail 0

$ grep -n -i -E "send|submit|fax|..." plugin/desktop/plugin.js
22: * control sends, submits, faxes, e-mails, or uploads anything to a payer).
26: * BR-4 (every draft is shown labeled "draft for human review"; there is no send or submit control
116:/** The label every draft carries (BR-4); a draft the backend sends without it is not shown. */
608: * @param {(caseId: string) => Promise<unknown>} send
611:async function addDocument(api, caseId, send) {
616:    await send(id);
$ grep -n -E "fetch\(|XMLHttpRequest|..." plugin/desktop/plugin.js
(no output)

$ uv run python -W ignore enum_routes.py
gateway: 15 routes; send-like: []
   GET /cases/{case_id}  GET /health  GET /models/status  GET /settings  POST /cases
   POST /cases/{case_id}/diagnose|documents|draft|draft/text|export|fields|paste|process
   POST /models/convert  POST /models/download
worker: 24 routes; send-like: []
   GET /cases/{case_id}  GET /corpus/audit|global|status  GET /health  GET /jobs/{job_id}/events
   GET /models/status  POST /cases  POST /cases/{case_id}/diagnose|documents|draft|draft/text|
   export|extract|fields|paste  POST /corpus/import|purge|reindex  POST /models/convert|download
   POST /models/{role}/load|unload  POST /redact

operator run (case_8b945401fcf346ca): process done, diagnose done, draft done, edited, confirmed,
copied to <scratch>/out73/appeal-draft-case_8b945401fcf346ca.pdf
copied to <scratch>/out73/appeal-draft-case_8b945401fcf346ca.docx
$ sort connects.log | uniq -c
   3 socket.connect ('127.0.0.1', 55637)
   1 socket.connect ('127.0.0.1', 55640)
   1 socket.connect ('127.0.0.1', 55639)
   1 socket.connect ('127.0.0.1', 55638)
after the worker stopped: exports folder empty; no listener on 18200-18299; no worker process left
```

Artifacts: `evidence/US-7.3/junit.xml`, `evidence/US-7.3/junit-node.xml`

## Notes

- Both criteria are checked against what exists today, through pinned tables, a source scan, and
  runtime walks. A new route or control is caught only if it changes a pinned table or matches
  the patterns. The node walk uses the fake SDK (`register-fakes.mjs`); the pane was not seen in a
  live Hermes desktop.
- The one route that may leave this Mac is `POST /models/download`, a user-confirmed model
  download (BR-1). It carries only a role and a yes/no, never case content. No real download was
  started in this run.
- The socket audit in the operator run covered only the worker process. It logged 6 connects,
  every one to `127.0.0.1`. HTTP keep-alive reuses connections, so the count is low. The gateway
  (`plugin_api.py` inside Hermes) was not part of the operator run. Its routes are covered by
  `test_us_7_3_case_routes_reach_only_loopback` and the pinned gateway table.
- The spec-delta scenario "A case's routes reach only loopback"
  (`openspec/changes/us-7-3-no-send-submit/specs/`) is `test_us_7_3_case_routes_reach_only_loopback`,
  backed by the operator socket audit above.
- How the operator run was isolated: a fresh scratch `HERMES_HOME`, run after the US-7.2 worker
  had stopped. It used the same harness as US-7.1, on 127.0.0.1:18216, with only synthetic data.
  The real `~/.hermes` was not touched.
