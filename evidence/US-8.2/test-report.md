# Test Report: US-8.2 Opt-In De-identified Aggregation and Weekly Summary

Change: us-8-2-weekly-summary
Story: US-8.2
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro), time zone America/Costa_Rica; Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; uvicorn 0.54.0

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Only opted-in profiles are aggregated: Then it includes outcomes from A and none from B" | PASS | `test_us_8_2_only_opted_in_profiles`: with `default` opted in (A: one overturned, one upheld) and `b` never opted in (B: two written off), the summary has `profiles == ["default"]`, `not_shared == 1`, totals 1/1/0 (total 2), and `sqlite3.connect` never received a path in B's user scope. Also `test_us_8_2_revoking_excludes_the_profile`, `test_us_8_2_sharing_needs_an_explicit_true` (`True` shares; `False`, `"yes"`, `1`, `None` do not), `test_us_8_2_sharing_fails_closed` (no config, unparseable YAML, another invalid setting), `test_us_8_2_summary_through_the_gateway`. Pane (node): `test_us_8_2_dashboard_shows_the_weekly_summary` calls `/outcomes/summary` and renders the sharing profiles, the `not_shared` count, and the totals. Operator: on a scratch worker, profile `alpha` (`share_outcome_stats: true`) closed 4 cases (2 overturned, 1 upheld, 1 written off), `beta` (no `share_outcome_stats`) closed 3 (all written off), and `gamma` (`share_outcome_stats: "yes"`) closed 1 (overturned). `make outcomes-summary WEEK=2026-W44` gave `profiles: ["alpha"]`, `not_shared: 2`, totals `2/1/1`, total 4, rate 0.5. These are alpha's counts exactly; none of beta's 3 written-off outcomes or gamma's overturned one is included. The SQLite trace for the request shows one `?mode=ro` connection, to alpha's `corpus.sqlite3` only. As a control, adding `share_outcome_stats: true` to beta gave `profiles: ["alpha","beta"]` and written off 4 (total 7), which shows beta's outcomes exist and were left out only because beta had not opted in. Revoking alpha (`false`) gave `profiles: []`, `not_shared: 3`, total 0, with 0 SQLite trace lines |
| 2 | "Aggregation never reads raw documents: Then it reads only the de-identified outcome tables and opens no source document" | PASS | `test_us_8_2_aggregation_reads_only_outcomes`: a case that holds a PHI fixture document is closed with an outcome; `CorpusStore.__init__` is patched to fail, every traced statement names `main.outcomes` and no other table (`documents`, `chunks`, `case_items`, `vectors`, `meta`, `audit_log`), and the summary contains no fixture string. `test_us_8_2_reader_can_open_nothing_else` (8 cases): under the reader's authorizer, `SELECT` from `documents`, `case_items`, `chunks`, `meta`, and `audit_log`, `ATTACH`, `PRAGMA table_info`, and `DELETE FROM outcomes` all raise `sqlite3.DatabaseError`, and `SELECT outcome FROM main.outcomes` still works. `test_us_8_2_reader_needs_no_key`, `test_us_8_2_reader_errors_are_corpus_errors`, `test_us_8_2_an_unreadable_profile_is_named`, `test_us_8_2_a_foreign_row_fails_only_its_profile`. Operator: each case had a pasted synthetic 835 as its source document. Across all 8 summary requests the worker made no other SQLite connection: each request opened only `file://…/user/corpus.sqlite3?mode=ro`, never `index.sqlite3` or the global store. Each request ran exactly two statements: `SELECT * FROM main.outcomes LIMIT 0` and `SELECT outcome, recorded_at, features FROM main.outcomes WHERE recorded_at >= … AND recorded_at < … ORDER BY recorded_at, rowid`. Neither the W44 output nor the worker log contains any string from the 835 (`CLAIM-77`, `PCN-0001`, `SYNTHETIC CLINIC`, `PATIENT`, `ACME HEALTH PLAN`, the NPI, `99213`, the service date, the amount) |

## Evidence Commands

```bash
make evidence STORY=US-8.2
make test-story STORY=US-8.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_8_2 -v
# operator run on a scratch worker: serve_summary_worker.py (scratchpad, not the repo) serves the
# real create_app with an InMemoryKeyProvider, a fake embedding server, fake classification and
# explanation servers, and the synthetic code notes and rule cards of tests/fakes/diagnosis.py;
# every sqlite3.connect in the process is traced (database, then each statement) to a scratch file
S=<scratch>/tester-8-2
export HERMES_HOME=$S/hermes MODELS_HOME=$S/models WORKER_PORT=18212
# profiles/alpha/config.yaml: plugins.entries.claimcoach.settings.share_outcome_stats: true
# profiles/beta/config.yaml:  plugins.entries.claimcoach.settings.retention_days: 90 (no share_outcome_stats)
# profiles/gamma/config.yaml: plugins.entries.claimcoach.settings.share_outcome_stats: "yes"
# per case: make case-new PROFILE=p; make case-paste PROFILE=p CASE=c FILE=$S/era.835;
#           make case-process ...; make case-diagnose ...; make case-outcome PROFILE=p CASE=c OUTCOME=o
#   alpha: overturned, upheld (prior_authorization), written_off (timely_filing), overturned (not diagnosed)
#   beta:  written_off x3;  gamma: overturned
make outcomes-summary WEEK=2026-W44
make outcomes-summary
make outcomes-summary WEEK=2027-W53     # also 2026-W54, 2026-W00, 9999-W52
make outcomes-summary WEEK=2026-44      # also W44, "2026-W44;x"
make outcomes-summary WEEK=2026-W53
# revoke alpha (share_outcome_stats: false), summarize, restore; opt beta in, summarize, restore
kill -TERM <worker pid>; lsof -nP -iTCP:18212 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-8.2
tests/test_us_8_2_weekly_summary.py .................................... [ 66%]
..................                                                       [100%]
- generated xml file: .../evidence/US-8.2/junit.xml -
===================== 54 passed, 1259 deselected in 2.12s ======================
junit-node.xml: 1 US-8.2 case (test_us_8_2_dashboard_shows_the_weekly_summary), failures 0

$ make test-story STORY=US-8.2
===================== 54 passed, 1259 deselected in 2.10s ======================
▶ US-8.2 only opted-in profiles are aggregated
  ✔ test_us_8_2_dashboard_shows_the_weekly_summary (2.760875ms)
ℹ tests 9  ℹ pass 9  ℹ fail 0      (8 file-level entries plus the one US-8.2 test)

$ uv run pytest ... -k us_8_2 -v   (54 PASSED, 0 failed), including
test_us_8_2_only_opted_in_profiles PASSED
test_us_8_2_revoking_excludes_the_profile PASSED
test_us_8_2_sharing_needs_an_explicit_true[True-True|False-False|yes-False|1-False|None-False] PASSED
test_us_8_2_sharing_fails_closed PASSED
test_us_8_2_aggregation_reads_only_outcomes PASSED
test_us_8_2_reader_can_open_nothing_else[...] PASSED (8)
test_us_8_2_reader_needs_no_key PASSED
test_us_8_2_counts_and_overturn_rate PASSED
test_us_8_2_a_case_counts_once_per_code PASSED
test_us_8_2_invalid_weeks[...] PASSED (10)
test_us_8_2_summary_through_the_gateway PASSED
test_us_8_2_bad_weeks_through_the_gateway[...] PASSED (7)
test_us_8_2_a_foreign_row_fails_only_its_profile PASSED

worker start: imported codes: ok=True imported={'code': 4}; imported rules: ok=True imported={'rule_card': 4}
              Uvicorn running on http://127.0.0.1:18212
cases closed (profile, case, outcome, diagnosis denial_reason):
alpha case_a4d96523724475ca overturned  prior_authorization
alpha case_df94c203c77a7bfe upheld      prior_authorization
alpha case_a6eb587ab2a3da47 written_off timely_filing
alpha case_f234b39de94c4ac4 overturned  None
beta  case_9c7b7d91b4740e7d written_off prior_authorization
beta  case_10e35993fde3171d written_off prior_authorization
beta  case_edba850fd34627ca written_off timely_filing
gamma case_c6e6283aec10e51e overturned  prior_authorization

$ make outcomes-summary WEEK=2026-W44
    "week": "2026-W44",
    "starts_at": "2026-10-26T06:00:00Z",
    "ends_at": "2026-11-02T06:00:00Z",
    "timezone": "America/Costa_Rica",
    "profiles": ["alpha"],
    "not_shared": 2,
    "unreadable": [],
    "totals": {"overturned": 2, "upheld": 1, "written_off": 1, "total": 4, "overturn_rate": 0.5},
    "by_category": [
      {"overturned": 1, "upheld": 1, "written_off": 0, "total": 2, "overturn_rate": 0.5,
       "payer": "ACME Health", "denial_reason": "prior_authorization"},
      {"overturned": 0, "upheld": 0, "written_off": 1, "total": 1, "overturn_rate": 0.0,
       "payer": "ACME Health", "denial_reason": "timely_filing"},
      {"overturned": 1, "upheld": 0, "written_off": 0, "total": 1, "overturn_rate": 1.0,
       "payer": null, "denial_reason": null}],
    "by_code": [
      {"overturned": 1, "upheld": 1, "written_off": 1, "total": 3, "overturn_rate": 0.3333,
       "payer": "ACME Health", "code": "CO-197"},
      {... same counts ..., "payer": "ACME Health", "code": "N286"}]
exit=0
SQLite trace during this request:
AnyIO worker thread  CONNECT file://<scratch>/hermes/profiles/alpha/plugin-data/claimcoach/user/corpus.sqlite3?mode=ro
AnyIO worker thread  SQL SELECT * FROM main.outcomes LIMIT 0
AnyIO worker thread  SQL SELECT outcome, recorded_at, features FROM main.outcomes WHERE recorded_at >= '2026-10-26T06:00:00+00:00' AND recorded_at < '2026-11-02T06:00:00+00:00' ORDER BY recorded_at, rowid

$ make outcomes-summary                 (no WEEK: last completed week)
    "week": "2026-W43",
    "starts_at": "2026-10-19T06:00:00Z",
    "ends_at": "2026-10-26T06:00:00Z",
    "timezone": "America/Costa_Rica",
    "profiles": ["alpha"], "not_shared": 2, "unreadable": [],
    "totals": {"overturned": 0, "upheld": 0, "written_off": 0, "total": 0, "overturn_rate": null},
    "by_category": [], "by_code": []
exit=0      (trace: the same single ro connection to alpha, bounds 2026-10-19T06:00 to 2026-10-26T06:00)
$ readlink /etc/localtime
/var/db/timezone/zoneinfo/America/Costa_Rica

$ make outcomes-summary WEEK=2027-W53   (also 2026-W54, 2026-W00, 9999-W52: identical)
curl: (22) The requested URL returned error: 422
{"ok": false, "error": {"code": "invalid_request", "message": "The request did not match the expected parameters."}}
make: *** [outcomes-summary] Error 22
exit=2      (no SQLite connection was made for any of the four)
$ make outcomes-summary WEEK=2026-44    (also WEEK=W44, WEEK="2026-W44;x")
usage: make outcomes-summary [WEEK=<ISO week, such as 2026-W44>]
make: *** [outcomes-summary] Error 2
exit=2
$ make outcomes-summary WEEK=2026-W53   (a 53-week year: accepted)
    "week": "2026-W53", "starts_at": "2026-12-28T06:00:00Z", "ends_at": "2027-01-04T06:00:00Z", "total": 0

opt-in changes (WEEK=2026-W44):
alpha revoked (false)      profiles=[]               not_shared=3 totals=o0/u0/w0 total=0 rate=None
                           SQLite trace lines during this request: 0
alpha restored (true)      profiles=['alpha']        not_shared=2 totals=o2/u1/w1 total=4 rate=0.5
beta opted in (control)    profiles=['alpha','beta'] not_shared=1 totals=o2/u1/w4 total=7 rate=0.2857
beta restored (no setting) profiles=['alpha']        not_shared=2 totals=o2/u1/w1 total=4 rate=0.5

SQLite connections from the first summary to the stop (8 successful summary requests):
   7 CONNECT file://<scratch>/hermes/profiles/alpha/plugin-data/claimcoach/user/corpus.sqlite3?mode=ro
   1 CONNECT file://<scratch>/hermes/profiles/beta/plugin-data/claimcoach/user/corpus.sqlite3?mode=ro   (the beta opt-in control only)
   0 to gamma, to any index.sqlite3, or to the global store
statements: 8 x "SELECT * FROM main.outcomes LIMIT 0", 8 x "SELECT outcome, recorded_at, features FROM main.outcomes WHERE …"

leak check: W44 summary output, lines matching CLAIM-77|PCN-0001|SYNTHETIC|PATIENT|ACME HEALTH PLAN|1234567893|99213|2026-09-01|250|case_ : 0
            worker log, the same case strings: 0
worker log: "a profile's share_outcome_stats is invalid; its outcomes are not shared" (gamma's "yes"; no profile name, no content)
after SIGTERM: Application shutdown complete; port 18212 free
```

Artifacts: `evidence/US-8.2/junit.xml`, `evidence/US-8.2/junit-node.xml`

## Failures

None.

## Notes

- The spec-delta scenarios (`openspec/changes/us-8-2-weekly-summary/specs/`) were exercised as
  follows:
  - "Only opted-in profiles are aggregated": row 1.
  - "Revoking the opt-in": `test_us_8_2_revoking_excludes_the_profile`. In the operator run,
    alpha with `share_outcome_stats: false` gave `profiles: []` and total 0, and its database was
    not opened (0 trace lines).
  - "Aggregation never reads raw documents": row 2.
  - "Counts and overturn rate": `test_us_8_2_counts_and_overturn_rate` and
    `test_us_8_2_a_case_counts_once_per_code`. In the operator run, ACME Health had
    prior_authorization at 1/1/0 (rate 0.5) and timely_filing at 0/0/1 (rate 0.0). The case that
    was never diagnosed counted under `payer: null, denial_reason: null` (rate 1.0) and in no code
    row. CO-197 and N286 each counted the 3 diagnosed cases once (rate 0.3333).
  - "An invalid week": `test_us_8_2_invalid_weeks` (10 cases) and
    `test_us_8_2_bad_weeks_through_the_gateway` (7 cases). In the operator run, `2027-W53`,
    `2026-W54`, `2026-W00`, and `9999-W52` were refused by the worker with 422 `invalid_request`,
    and malformed values were refused by `make` with its usage line (exit 2).
- How the operator run was isolated: `serve_summary_worker.py` lives in the session scratchpad
  (`.../scratchpad/tester-8-2/ops/`), not the repo. It follows the US-7.1 harness. It serves the
  real `create_app` with `HERMES_HOME` and `MODELS_HOME` set to the scratch directory, an
  `InMemoryKeyProvider` (no Keychain item), and in-process `FakeModelServer`s for embedding,
  classification, and explanation, on 127.0.0.1:18212 with `WORKER_PORT=18212`. A control file
  switched the fake classifier's `denial_reason` between `prior_authorization` and
  `timely_filing`, which produced two categories. All data was synthetic (the US-5.1 `ERA_835`
  and the rule cards and code notes of `tests/fakes/diagnosis.py`). The worker was stopped with
  SIGTERM and port 18212 was free afterwards. My harness's `finally` did not run under SIGTERM,
  so I deleted the scratch token file by hand. The real `~/.hermes` was not touched.
- How row 2 was checked: the SQLite trace is the harness's own wrapper around `sqlite3.connect`,
  which `corpus.store.read_outcomes` calls, plus a trace callback on every connection. It records
  SQLite activity in the worker process, not every file the process opens; I did not run
  `fs_usage` or `dtrace` (they need root). Source documents live only inside each profile's
  `corpus.sqlite3`: the scratch tree holds no other case files, only the databases, the configs,
  and the token. The tests rule out any other path: `CorpusStore.__init__` patched to fail, and
  the authorizer refusing every other table.
- Default week: today (Saturday 2026-10-31) is in 2026-W44, so `make outcomes-summary` with no
  `WEEK` summarized 2026-W43, Monday 2026-10-19 00:00 to Monday 2026-10-26 00:00 in
  America/Costa_Rica (UTC-6, no daylight-saving time). That week holds none of the outcomes I
  recorded, so its counts were 0. No outcome could be recorded inside a past week without
  changing the clock, so the default-week path was checked against real counts only by
  `test_us_8_2_default_week_and_zone` and `test_us_8_2_last_completed_week_is_judged_locally`.
  This Mac's zone has no daylight-saving time, so weeks of 167 or 169 hours were not seen in the
  operator run. They are covered by `test_us_8_2_week_bounds_in_the_local_zone` (America/New_York).
- The dashboard: the node test renders it under `register-fakes.mjs`. It was not seen in a live
  Hermes desktop, and the Settings → Plugins toggle that writes `share_outcome_stats` was not
  used. I wrote the `config.yaml` entries by hand in the shape the runbook gives.
- Things I noticed, outside this story's criteria:
  - The 422 for a week that does not exist has the generic message "The request did not match
    the expected parameters." It does not say the week is the problem.
  - A profile whose setting is invalid (gamma, `"yes"`) is counted in `not_shared` like one that
    never opted in. The worker logs a warning without the profile name, so the manager cannot
    tell from the summary that a profile tried to opt in with an invalid value. This is what
    design decision 3 and the runbook describe.
  - As with earlier stories, a refused `make outcomes-summary` shows curl's `Error 22` from the
    recipe, and `make` itself exits 2.
