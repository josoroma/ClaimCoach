# Test Report: US-10.3 Settings Page for Models, Corpus, and Retention

Change: us-10-3-settings-page
Story: US-10.3
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (`~/.hermes/hermes-agent`, venv Python 3.11.15, `hermes_cli.plugins_settings` writer); no live Hermes Desktop

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Settings page registers when supported: Then a ClaimCoach settings page is registered" | PASS | `test_us_10_3_settings_registers_when_supported` (node; the fake ctx provides `registerSettingsPage`): one settings page is recorded with id `settings`, title `ClaimCoach`, and icon `gear`. Its render has the sections `Models`, `Corpus`, and `Retention`. Operator: the page's own loaders (`loadModels`, `loadCorpus`, `loadRetention` from `plugin.js`), run against a scratch gateway in Hermes' Python over the scratch worker, answered models `ok` (8 roles, `unloaded`, weights missing, venv missing; nothing loaded), corpus `{global: 0 documents, not encrypted; user: 3 cases, 2 documents, encrypted}`, and retention `{state: ok, days: 90}` |
| 2 | "Settings degrade when unsupported: Then registration completes without error" | PASS | `test_us_10_3_settings_degrade_when_unsupported` (node; `createFakeCtx({settingsPages: false})`, so the ctx has no `registerSettingsPage`): `register(ctx)` does not throw, no settings page is recorded, and the pane still registers. `plugin.js` calls `ctx.registerSettingsPage?.(...)` (feature-detected), and `tsc --checkJs` passes |
| 3 | "Retention setting is saved: Then the worker reads the new retention period" | PASS | Page: `test_us_10_3_pane_retention_saved` (node). The page loads 90 without the worker, the biller types `30`, and **Save** posts `{retention_days: 30}` to `/settings/retention`. The result is `{state: 'saved', days: 30}`, the stored value shows 30, and the text reads "...more than 30 days ago". Gateway (Python): `test_us_10_3_retention_saved` (writer called with `('claimcoach', PLUGIN_DIR, {retention_days: 30})`; `load_retention_days` and `RetentionPolicy.for_profile` read 30). `test_us_10_3_retention_saved_with_hermes` (`-m hermes`) passes against Hermes' real writer in Hermes' Python: saved 200 with 30, `0` refused 422, worker reads 30. Operator, run 2: a `POST /settings/retention {"retention_days":30}` through the scratch gateway returned 200. Hermes' writer created the scratch `config.yaml` (0600) with `retention_days: 30`. `load_retention_days` and `RetentionPolicy` read 30. The worker's next scheduled purge logged "removed the content of 1 cases". That case was `case_000000000000a045`, closed 45 days ago, which the earlier runs at 90 days had kept. The case closed 10 days ago was kept. Run 3, from `plugin.js` `saveRetention(rest, 45)`: the answer was `saved 45`, with "Saved. The next purge removes the content of cases closed more than 45 days ago." The next scheduled purge purged the 45-day case and kept the 10-day case |

## Evidence Commands

```bash
make evidence STORY=US-10.3
make test-story STORY=US-10.3
uv run pytest -m hermes -p no:cacheprovider --no-cov -rs -v --durations=1 tests/test_us_10_3_settings_page.py
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/desktop_ui.test.mjs
npm exec --no -- tsc --noEmit -p tsconfig.json
# operator run (harness in the session scratchpad, tester-10/; setup as in the US-10.1 report):
# scratch worker 127.0.0.1:18216 (real create_app; its RetentionJob interval set to 30 s instead of
# 6 h; seeds synthetic cases closed 45 and 10 days ago), scratch gateway 127.0.0.1:18217 (the
# plugin_api.py router in Hermes' venv Python, Hermes' own hermes_cli on PYTHONPATH),
# HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models (empty)
G=http://127.0.0.1:18217/api/plugins/claimcoach
curl $G/settings; curl $G/models/status; curl $G/corpus/status
curl -X POST -H 'Content-Type: application/json' -d '<body>' $G/settings/retention   # 5 bad bodies
curl -X POST -H 'Content-Type: application/json' -d '{"retention_days":30}' $G/settings/retention
grep -n "retention_days" "$HERMES_HOME/config.yaml"                                    # runbook check
uv run --no-sync python -c "load_retention_days(home); RetentionPolicy.for_profile(home).days"
# wait for the next scheduled purge, then:
cat <scratch>/worker.log; make case-list; curl ... /corpus/audit
make corpus-purge; curl -X POST ... -d '{}' http://127.0.0.1:18216/corpus/purge
make case-new PROFILE=biller-b; curl ...18216/corpus/status; curl $G/corpus/status    # profile filter
kill -TERM <worker>; curl $G/{models/status,corpus/status,settings}; bridge.mjs       # worker down
# run 3 (fresh scratch root): bridge.mjs save -> saveRetention(rest, 0) and (rest, 45); next purge
GATEWAY_PORT=18217 node --import ./plugin/desktop/tests/register-fakes.mjs <scratch>/bridge.mjs save
kill -TERM <worker> <gateway>; lsof -nP -iTCP:18216 -sTCP:LISTEN; lsof -nP -iTCP:18217 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-10.3
tests/test_us_10_3_settings_page.py ................                     [100%]
- generated xml file: .../evidence/US-10.3/junit.xml -
===================== 16 passed, 1527 deselected in 1.85s ======================
junit.xml: tests=16 failures=0 errors=0 skipped=0
  test_us_10_3_retention_saved, _retention_refusals (8), _retention_needs_json,
  _hermes_refuses_the_save[403-settings_managed | 503-settings_unavailable],
  _outside_hermes_nothing_is_saved, _corpus_status_shows_this_profile_only,
  _corpus_status_when_the_worker_is_down, _retention_saved_with_hermes
junit-node.xml: failures 0
  test_us_10_3_settings_registers_when_supported, test_us_10_3_settings_degrade_when_unsupported,
  test_us_10_3_pane_retention_saved

$ uv run pytest -m hermes ... tests/test_us_10_3_settings_page.py
tests/test_us_10_3_settings_page.py::test_us_10_3_retention_saved_with_hermes PASSED [100%]
0.52s call     tests/test_us_10_3_settings_page.py::test_us_10_3_retention_saved_with_hermes
======================= 1 passed, 15 deselected in 0.86s =======================

$ make test-story STORY=US-10.3
===================== 16 passed, 1527 deselected in 1.80s ======================
  ✔ test_us_10_3_settings_registers_when_supported
  ✔ test_us_10_3_settings_degrade_when_unsupported
  ✔ test_us_10_3_pane_retention_saved
ℹ tests 13  ℹ pass 13  ℹ fail 0
desktop_ui.test.mjs (whole file): ℹ tests 21  ℹ pass 21  ℹ fail 0
tsc --noEmit: exit 0

GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":90} HTTP 200
GET /models/status -> True: extraction | phi_detection | classification | embedding | rerank |
  explanation | drafting | transcription: unloaded weights missing venv False
GET /corpus/status -> global docs 0 encrypted False; user default cases 4 docs 2 encrypted True

{"retention_days":0} | {"retention_days":3651} | {"retention_days":"30"} |
{"retention_days":30,"richer_agent_access":true} | {}
  -> {"ok":false,"error":{"code":"invalid_request",...}} HTTP 422   (each)
config.yaml after refusals: No such file or directory
02:30:43 save {"retention_days":30} -> {"ok":true,"richer_agent_access":false,"retention_days":30} HTTP 200
$ grep -n "retention_days" "$HERMES_HOME/config.yaml"
5:        retention_days: 30
-rw------- <scratch>/hermes/config.yaml
GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":30}
worker reader: load_retention_days 30 RetentionPolicy.days 30

worker.log:
  02:30:07.486 "retention purge removed the content of 0 cases"   (90 days)
  02:30:37.488 "retention purge removed the content of 0 cases"   (90 days)
  02:31:07.494 "retention purge removed the content of 1 cases"   (first run after the save)
$ make case-list
  case_000000000000a010 closed 2026-10-22T02:30:07.473147Z purged None
  case_000000000000a045 closed 2026-09-17T02:30:07.472421Z purged 2026-11-01T02:31:07.491273Z
audit: {'seq': 13, 'at': '2026-11-01T02:31:07.491835Z', 'action': 'case_purged', 'case_id': 'case_000000000000a045', 'profile': 'default'}
$ make corpus-purge
error: worker_unavailable                      (expected against this harness; see Notes)
POST /corpus/purge {} -> {"ok":true,"reports":[{"profile":"default","cases":[],...}],"skipped":[]}

worker GET /corpus/status user scopes: ['default', 'biller-b']
gateway (default profile) GET /corpus/status user scopes: ['default']

worker stopped:
GET /models/status | /corpus/status -> {"ok":false,"error":{"code":"worker_unavailable",...}} HTTP 503
GET /settings -> {"ok":true,"richer_agent_access":false,"retention_days":30} HTTP 200
bridge.mjs: models: unavailable; corpus: {"state":"unavailable"}; retention: {"state":"ok","days":30}

run 3, bridge.mjs save (fresh scratch root, worker up):
models: ok 8
corpus: {"state":"ok","global":{"cases":0,"documents":0,"encrypted":false,"available":true},"user":{"cases":3,"documents":2,"encrypted":true,"available":true}}
retention: {"state":"ok","days":90}
save 0: {"state":"refused","code":"invalid_request"} -> Enter a whole number of days from 1 to 3650.
save 45: {"state":"saved","days":45} -> Saved. The next purge removes the content of cases closed more than 45 days ago.
retention after: {"state":"ok","days":45}
config.yaml: 5:        retention_days: 45
worker.log: 02:32:24.844 removed 0 cases | 02:32:54.854 "retention purge removed the content of 1 cases"
  case_000000000000a010 closed 2026-10-22T02:32:24.831167Z purged None
  case_000000000000a045 closed 2026-09-17T02:32:24.830485Z purged 2026-11-01T02:32:54.848995Z
  case row: case_000000000000a045: opened 2025-09-27 · New · 0 document(s) · content purged

after SIGTERM: ports 18216 and 18217 free; no harness process left
~/.hermes/config.yaml: same mtime (1792951429) and sha1 (50907efc...) before and after
worker logs: 0 matches each for Jane, ACME, SYN-0001, SYNTH, CO-197
```

Artifacts: `evidence/US-10.3/junit.xml`, `evidence/US-10.3/junit-node.xml`

## Failures

None.

## Notes

- Spec-delta scenarios (`openspec/changes/us-10-3-settings-page/specs/settings-page/spec.md`):
  - "Settings page registers when supported", "Settings degrade when unsupported", and
    "Retention setting is saved" are rows 1 to 3.
  - "Retention cannot be saved": an invalid body, a missing Hermes writer, or a managed key is
    refused with `invalid_request`, `settings_unavailable`, or `settings_managed`, and nothing is
    written. PASS. `test_us_10_3_retention_refusals` covers 8 bodies,
    `_retention_needs_json` covers a form body (422) and an oversized body (413
    `document_too_large`), `_hermes_refuses_the_save` covers 403 `settings_managed` and 503
    `settings_unavailable` (Hermes' message is neither shown nor logged), and
    `_outside_hermes_nothing_is_saved` covers 503. The page side is "a refused save keeps the
    typed value". Operator: five bad bodies got 422 `invalid_request`, and no `config.yaml` was
    created. That includes `retention_days` sent together with `richer_agent_access`. A managed
    install and a missing writer were not reproduced in the operator run; they are covered by
    the tests only.
  - "Another profile's scope is not shown": PASS. `test_us_10_3_corpus_status_shows_this_profile_only`.
    Operator: the worker reported the `default` and `biller-b` user scopes, and the gateway (the
    default profile) answered `default` only.
- No live Hermes Desktop: Settings → **ClaimCoach** in a real host was not seen. Also not seen:
  typing in the field, pressing **Save**, and the managed-install message. Whether this Hermes
  Desktop build provides `ctx.registerSettingsPage` was not observed either. Rows 1 and 2 are
  PASS on the named node tests with the fake ctx, which is what their "Given a host whose ctx
  provides / lacks registerSettingsPage" describes. The live page stays UNVERIFIED. Row 3 was
  exercised through the page's own `saveRetention`/`loadRetention` code, the real gateway
  router, and Hermes' real writer. The host's `ctx.rest` was replaced by `fetch` in
  `bridge.mjs`.
- The worker reads the period live: `RetentionPolicy.for_profile` reads the profile's
  `config.yaml` on every purge run, and no restart is needed. The scheduled job normally runs
  every six hours. The harness shortened it to 30 s by setting
  `RetentionJob.__init__.__kwdefaults__`, so the next run could be observed. The purge code and
  schedule loop are otherwise unchanged. The runbook's "within six hours" was not waited out.
- `make corpus-purge` printed `error: worker_unavailable` against this harness. This is
  expected, as in US-7.1, US-8.1, and US-11.1: the corpus CLI sends the token only to a worker
  that the launcher recorded in its PID file. I posted the same purge to `/corpus/purge` with
  curl; it had nothing more to purge.
- When no `config.yaml` exists, Hermes' writer creates one from Hermes' commented template
  (mode 0600) holding only the plugin's `retention_days` entry. That is Hermes' behaviour, noted
  for operators who `grep` the file.
- The **Models** section was fed by a status-only `ModelManager` over an empty scratch
  `MODELS_HOME`, so every role reads `unloaded`, weights missing, venv missing. The
  present/ready path is covered by the node test "model and corpus sections show status or a
  fixed error" only. No model was loaded or downloaded.
- How the operator run was isolated: as in the US-10.1 report. The scratchpad harness refuses
  non-scratch paths, uses an `InMemoryKeyProvider`, and runs on ports 18216 and 18217. All data
  was synthetic. The real `~/.hermes/config.yaml` was unchanged, and both ports were free after
  SIGTERM.

## Re-verification after the review fixes

The independent review (`openspec/changes/us-10-3-settings-page/review.md`) led to fixes in the pane and the
gateway after the tester's run above, so the implementer recorded the evidence again:

```bash
make evidence STORY=US-10.3
make check
```

```text
junit.xml: tests=27 failures=0; junit-node.xml: tests=3 failures=0
TOTAL    7102      0   1180      0   100%
=============== 1544 passed, 10 deselected in 180.19s (0:03:00) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
```

The operator run above predates the fixes; the review's regression tests are listed in its
Findings and resolution table.
