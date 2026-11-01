# Test Report: US-12.4 Zero-Egress Check for Case Content

Change: us-12-4-zero-egress-check
Story: US-12.4
Verdict: pass
Coverage: 7/8 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; `/usr/sbin/lsof` present (`make doctor`: `ok lsof`); no ClaimCoach worker running (`make worker-status`: `not running`); the user's `~/.hermes/plugin-data/claimcoach/models.yaml` fails validation (`python -m claimcoach.models check`)

## Acceptance Criteria Evaluated

Row 1 is the SPECS.md scenario, run against fake model servers that listen inside the worker
process. Rows 2 to 7 are the extra scenarios in the change spec. Row 8 is the scenario as written,
"all required models are present" with real model-server processes, and it was not run (see
Notes). I tested the plugin as of 22:29 and the tests as of 22:37.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "A full case flow makes no non-loopback connection: Then no network connection to a non-loopback address is opened by the worker, plugin_api, or model servers" | PASS | `test_us_12_4_full_flow_no_non_loopback_connection` passes on the EOB-PDF case: `flow_completed` (upload, extract, diagnose, draft, export) with no findings. Real `/usr/sbin/lsof` sampled the process that hosts the worker app and the fake model servers, and every remote was `127.0.0.1` or `::1`. Also passing: `_a_stopped_flow_does_not_pass`, `_one_sample_always_follows_the_flow`, `_cli_writes_the_report`, and `test_us_12_3_flow_exports_the_draft`. Operator run: `make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good` against a scratch loopback worker over fake models, with `GET /egress` served by the real `EGRESS_AUDIT.status()` (`{"ok":true,"audit":true,"dropped":0}`), printed `US-12.4 egress: flow completed, 2 samples of plugin_api:97411, worker:97393, 0 non-loopback: PASS` and exited 0. `egress.json` has `findings: []`, `passed: true`, and `observers {plugin_api: [audit], worker: [audit, lsof]}`. The default `EVAL_OUT` is `evidence`, so the default path is `evidence/US-12.4/egress.json` |
| 2 | "A non-loopback attempt is recorded (change spec): THEN a record with event `connect`, host `192.0.2.10`, and port 443 is appended" | PASS | Passing: `test_us_12_4_audit_hook_keeps_only_non_loopback`, `_record_file_is_owner_only`, `_audit_hook_is_added_once`, and `_worker_starts_the_audit` (the worker's `main` starts the hook before the registry loads and serves with `loop="asyncio"`). `_plugin_api_attempt_is_caught` makes a real UDP `connect()` to 203.0.113.7:443, which sends no packet. Operator run: the scratch worker's drafting fake raised a `socket.connect` audit event for `("192.0.2.10", 443)` (via `sys.audit`; no packet was sent). `worker/egress.jsonl` (`-rw-------`) then held `{"at":"2026-11-01T04:36:06.571708Z","process":"worker","pid":96853,"event":"connect","host":"192.0.2.10","port":443}`, which is time, process, PID, event, host, and port only |
| 3 | "Loopback is not recorded (change spec): WHEN the worker connects to a model server on 127.0.0.1 THEN nothing is recorded" | PASS | `test_us_12_4_audit_hook_keeps_only_non_loopback` passes; it records nothing for `127.0.0.1`, `::1`, `localhost`, a Unix socket, `getaddrinfo(None)`, or `b"127.0.0.1"`. Operator run: after the "good" round (64 flows, all calling the fake model servers on 127.0.0.1) and again after the real-audit egress run, `worker/egress.jsonl` was 0 bytes (`-rw-------`, created up front by `file_sink`) |
| 4 | "A record that cannot be written does not break the call (change spec): THEN the socket call goes on and `GET /egress` counts the attempt as dropped" | PASS | Passing: `test_us_12_4_a_failing_sink_never_breaks_the_socket_call` (`dropped == 1`, `status() == EgressStatus(audit=True, dropped=1)`) and `_records_the_worker_could_not_write_are_a_finding` (a growing `dropped` gives a `worker`/`unrecorded` finding, not passed). Operator run in "leak" mode with `egress.jsonl` set to mode 000: `GET /egress` went from `{"audit":true,"dropped":0}` to `{"audit":true,"dropped":1}` after the flow. The worker kept serving, and the eval case was created, ran, and was purged (`purged_at` set, 0 documents). See Notes for how the CLI then ended |
| 5 | "A worker started before the audit existed (change spec): WHEN the running worker answers `audit: false` THEN the check exits 2 and says to restart the worker" | PASS | `test_us_12_4_worker_without_its_audit_is_not_measured` (no case created), `_cli_refuses_a_worker_without_its_audit`, `_worker_without_a_record_file_serves_with_the_audit_off`, and `_worker_reports_its_audit` (`GET /egress` without the bearer token gives 401) pass. Operator run: the scratch worker ran without the hook (`GET /egress`: `{"ok":true,"audit":false,"dropped":0}`). `make eval-egress` printed `not measured: the worker's egress audit is not recording; restart it (make stop, make start)`, then `make: *** [eval-egress] Error 2`. No report was written, and `make case-list` showed 0 cases |
| 6 | "A connection beyond loopback fails the check (change spec): THEN the check exits non-zero and names the process, the address, and the port" | PASS | Passing: `test_us_12_4_lsof_connection_is_caught` (an lsof sample from a child of the worker's group showing `->93.184.216.34:443` gives `BLOCKED` and the line `lsof worker:<pid> connect 93.184.216.34:443`), `_worker_records_during_the_flow_are_caught` (only records appended during the flow count), and `_cli_blocks_on_a_finding` (exit 1). Operator run in "leak" mode: `make eval-egress` printed `flow completed, 2 samples of plugin_api:96883, worker:96853, 1 non-loopback: BLOCKED` and the line `audit worker:96853 connect 192.0.2.10:443`, then `make: *** [eval-egress] Error 1`. The finding in `egress.json` is `{source: audit, process: worker, pid: 96853, event: connect, host: 192.0.2.10, port: 443}`. A second run (`EVAL_CASE=denial_001`) reported only its own new record (1 finding), while `egress.jsonl` then held 2 |
| 7 | "A download in progress is not measured (change spec): THEN the check exits 2 without running the flow" | PASS | Passing: `test_us_12_4_preconditions` (`transcription: downloading` and `rerank: converting` count as problems; a missing `transcription` alone does not), `_cli_needs_every_case_model` (exit 2, no report), `_lsof_failure_is_an_error` x4, `_process_lookup_failure_is_a_tool_error`, `_sampler_failure_stops_the_flow`, and `_cli_no_worker`. Operator runs: with the extraction model's `model.safetensors` moved away, `make eval-egress` printed `not measured: extraction: weights missing` and `Error 2`, and `EVAL_OUT` was not created. `EVAL_CASE=denial_999` printed `not measured: no case denial_999 in tests/fixtures/denials/denial_set.json`. With no worker it printed `not measured: the worker on port 18200 answered worker_unavailable`. The "downloading" state itself was exercised only by the unit test, not with a live download |
| 8 | "A full case flow makes no non-loopback connection: Given all required models are present and no download or import is in progress" (real model-server processes, `test_us_12_4_full_flow_on_the_running_app`, marked `models`) | UNVERIFIED | `uv run pytest -m models -k us_12_` reported `SKIPPED ... no ClaimCoach worker on port 18200`. No real model-server process (`model:<role>` in `processes`/`observers`) was ever sampled. The operator reports list only `plugin_api` and `worker` |

## Evidence Commands

```bash
make test-story STORY=US-12.4
make evidence STORY=US-12.4
uv run pytest -m models -p no:cacheprovider --no-cov -k "us_12_" -rs
make -n eval-egress; make doctor | grep lsof
# no worker; scratch homes
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models
make eval-egress EVAL_OUT=<scratch>/out2/none
# scratch loopback worker over fake models on 18217 (see the US-12.1 report). It starts
# EGRESS_AUDIT("worker", file_sink(<state_dir>/egress.jsonl)) as worker/__main__.py does (except in
# mode "noaudit"), drops eval_worker's GET /egress override so the real EGRESS_AUDIT.status()
# answers, and uses tests/fakes/model_env.build_model_env (fake weights) as its ModelManager.
# Mode "leak": the drafting fake raises sys.audit("socket.connect", sock, ("192.0.2.10", 443)).
export HERMES_HOME=<scratch>/w/hermes MODELS_HOME=<scratch>/w/models
curl -s --noproxy '*' -H "Authorization: Bearer <token>" http://127.0.0.1:18217/egress
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/good-real-audit                # mode good
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/leak                           # mode leak
cat <scratch>/w/hermes/plugin-data/claimcoach/worker/egress.jsonl
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/leak2 EVAL_CASE=denial_001
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/leak3 EVAL_CASE=denial_999
mv <modelenv>/Models/Qwen3-VL-8B-Instruct-4bit/model.safetensors{,.away}
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/noweights; mv back
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/noaudit                        # mode noaudit
chmod 000 <scratch>/w/.../worker/egress.jsonl                                            # mode leak
make eval-egress WORKER_PORT=18217 EVAL_OUT=<scratch>/out2/dropped; curl .../egress; make case-list WORKER_PORT=18217
pkill -TERM -f "serve_eval_worker.py -m claimcoach.worker"; lsof -nP -iTCP:18217 -sTCP:LISTEN
```

```text
$ make test-story STORY=US-12.4
===================== 40 passed, 1653 deselected in 19.10s =====================
$ make evidence STORY=US-12.4          # after the 22:37:52 test edit
===================== 41 passed, 1654 deselected in 19.35s =====================
junit.xml: tests=41 failures=0 errors=0 skipped=0 timestamp=2026-10-31T22:38:05
$ make evidence STORY=US-12.4          # implementer, after the fix for Notes observation 3
===================== 43 passed, 1654 deselected in 22.05s =====================
$ uv run pytest -m models -k us_12_ -rs
SKIPPED [4] tests/fakes/evals.py:176: no ClaimCoach worker on port 18200; start it with make start

$ make -n eval-egress
uv run python -m claimcoach.evals egress --out "$EVAL_OUT" --port 18200 --set "$DENIAL_SET" ${EVAL_CASE:+--case "$EVAL_CASE"}
$ make doctor | grep lsof
  ok       lsof
$ make eval-egress            # no worker
not measured: the worker on port 18200 answered worker_unavailable
make: *** [eval-egress] Error 2

# mode good, real audit status
{"ok":true,"audit":true,"dropped":0}
US-12.4 egress: flow completed, 2 samples of plugin_api:97411, worker:97393, 0 non-loopback: PASS
report: <scratch>/out2/good-real-audit/US-12.4/egress.json
-rw-------  0 bytes  .../worker/egress.jsonl
egress.json (good): "observers": {"plugin_api:96253": ["audit"], "worker:95640": ["audit", "lsof"]}, "findings": [], "passed": true

# mode leak
US-12.4 egress: flow completed, 2 samples of plugin_api:96883, worker:96853, 1 non-loopback: BLOCKED
  audit worker:96853 connect 192.0.2.10:443
make: *** [eval-egress] Error 1
-rw-------  117 bytes  .../worker/egress.jsonl
{"at":"2026-11-01T04:36:06.571708Z","process":"worker","pid":96853,"event":"connect","host":"192.0.2.10","port":443}
$ ... EVAL_CASE=denial_001
US-12.4 egress: flow completed, 2 samples of plugin_api:96943, worker:96853, 1 non-loopback: BLOCKED
  audit worker:96853 connect 192.0.2.10:443
$ ... EVAL_CASE=denial_999
not measured: no case denial_999 in tests/fixtures/denials/denial_set.json
$ ... (extraction weights moved away)
not measured: extraction: weights missing
make: *** [eval-egress] Error 2
ls: <scratch>/out2/noweights: No such file or directory

# mode noaudit
{"ok":true,"audit":false,"dropped":0}
not measured: the worker's egress audit is not recording; restart it (make stop, make start)
make: *** [eval-egress] Error 2
ls: <scratch>/out2/noaudit: No such file or directory; case-list: 0 cases

# mode leak, egress.jsonl chmod 000
{"ok":true,"audit":true,"dropped":0}          # before
not measured: unexpected PermissionError
make: *** [eval-egress] Error 2
{"ok":true,"audit":true,"dropped":1}          # after
case-list: [('case_4d63e27a8b37633a', purged=True, documents=0, drafted=False)]

$ lsof -nP -iTCP:18217 -sTCP:LISTEN     # after stopping the scratch worker
nothing listens on 18217
```

Artifacts: `evidence/US-12.4/junit.xml`

## Failures

None.

## Notes

- Row 8 is **UNVERIFIED**, and it is the claim the story exists to prove: that real
  `mlx_lm`/`mlx_vlm` model servers (separate process groups, which could reach a model hub) open
  nothing beyond loopback during a case flow. Offline and in my operator runs, the model servers
  were `FakeModelServer` threads inside the sampled process, so no `model:<role>` process appears
  in any report. No worker runs. As instructed, I did not start one, download models, edit
  `models.yaml`, or touch `~/.hermes`. The user's `models.yaml` fails validation. There is no
  `evidence/US-12.4/egress.json`. Even on real models, a model server is covered by `lsof` only
  (the report's `observers` say so): a DNS lookup or a connection between two samples is not seen.
- In the operator runs, my scratch process started the audit hook itself, mirroring
  `worker/__main__.py`. The real worker's own installation is covered by
  `test_us_12_4_worker_starts_the_audit`, not by a live `python -m claimcoach.worker`. The leak
  was a synthetic `sys.audit("socket.connect", ...)`, so no packet left the Mac. The lsof-sourced
  finding (row 6) was exercised only with canned lsof output.
- Row 4 operator detail: I simulated "cannot be written" with `chmod 000`. That also made the file
  unreadable to the checker, which runs as the same user. The worker counted the attempt as
  dropped and kept serving, which is what row 4 asks. The checker, though, failed when it read
  `egress.jsonl` after the flow, and printed `not measured: unexpected PermissionError` (exit 2).
  That outcome is safe (the release is blocked and the case was purged), but an operator gets no
  hint of what went wrong. The spec's own case, a full disk with a readable file, gives the
  `unrecorded` finding instead; that path was observed only in
  `test_us_12_4_records_the_worker_could_not_write_are_a_finding`.
- The check refuses to run during a model download or conversion, or with missing weights. It
  does not check for a corpus import in progress, the other half of the SPECS Given; the runbook
  leaves that to the operator. A concurrent import would show up as a finding (a false BLOCKED),
  not hide one.
- `tests/fakes/evals.eval_worker` answers `GET /egress` with `audit: true` by default, whatever
  the process's real hook state. My first "noaudit" attempt therefore passed until I removed that
  override. This is a test-harness default, not a product issue.
- The code changed while I was testing: `GET /egress`, `observers`, process-group sampling, and
  the dropped count were added at 22:26 to 22:29. During that window, 12 US-12.4 tests failed
  against the half-edited tree. This report records the second round, on the updated code (see
  the US-12.1 report Notes).
- Exit codes through Make: a blocked egress check and an unmeasured one both make `make` return 2.
  Only `Error 1` / `Error 2` tells them apart (see the US-12.1 report).
- The egress report records `flow_completed` but not which steps ran. "Through draft and export"
  is asserted by the tests (`test_us_12_3_flow_exports_the_draft`), not visible in `egress.json`.

Follow-up by the implementer, after this run: the unreadable-`egress.jsonl` observation above is
fixed. The check now stops with `not measured: the worker's egress record file
(worker/egress.jsonl) cannot be read; check its owner and mode (0600)` (exit 2), covered by the
two new tests `test_us_12_4_unreadable_worker_log_is_not_measured` and
`test_us_12_4_worker_log_that_cannot_be_statted_is_not_measured`; `junit.xml` was re-recorded
with 43 passing tests. The rows above are otherwise unchanged.
