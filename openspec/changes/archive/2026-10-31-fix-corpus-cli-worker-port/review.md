# Review: fix-corpus-cli-worker-port

Change: fix-corpus-cli-worker-port
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the files in scope, not the implementer's reasoning), 2026-10-31
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| low | `_client(port)` sent the data dir's worker token to whatever listened on `127.0.0.1:<port>`; the range also holds the model servers, so a mistyped `--port` (or a process of another user bound to a port) could receive a token that opens case content | The token is sent only when the launcher's PID file records the running worker at that `base_url` (`worker_status`, which also checks the process); otherwise `worker_unavailable` and nothing is sent; design decision 4, a new spec scenario; `test_us_4_3_corpus_cli_sends_the_token_only_to_the_recorded_worker` (a listener on the port receives no request, with the worker recorded elsewhere or not running) |
| low | The runbook presented another port as an ordinary setup, though the pane and gateway always use 18200 and a second worker needs its own data dir | The runbook says another port is for a scratch or test worker with its own `HERMES_HOME`, passed to the corpus targets too, and that other ports answer `worker_unavailable`; `test_us_4_3_corpus_runbook_names_the_worker_port` |
| low | The spec said `make corpus-*` pass `WORKER_PORT`, which read literally includes the local targets that must not | The spec names the six worker-backed targets and says the local ones pass none |
| info | The tests left out `key-import` (refusing `--port`) and the restore and key targets (no `--port` in `make -n`) | Both added to `test_us_4_3_corpus_cli_port_defaults_and_scope` and `test_us_4_3_corpus_targets_pass_worker_port` |
| info | Task 1.3's check only looked at runbook headings | `test_us_4_3_corpus_runbook_names_the_worker_port` checks the content |
| info | design.md showed `:=` where the Makefile uses `=`; tasks unticked | design.md matches; tasks ticked before archive |
| info | No test runs `make corpus-list` end to end | Not needed (reviewer): the `make -n` half and the live-port CLI half together cover it |

Also checked by the reviewer and found sound: `_port`'s range boundaries and fixed error text (BR-14); the out-of-range path stopping in `parse_args` with exit 2 before anything is read; the shared parent parser on exactly the six commands; the host literal `127.0.0.1` and `trust_env=False` (BR-1); restore and `make stop` reading the PID file, not the port.

## Re-verification

`make verify` → exit 0 on the fixed tree (2026-10-31): ruff, ruff format, biome, mypy --strict ×2,
tsc --checkJs; 1086 offline pytest tests passed at 100% line and branch coverage of `plugin/`
(including the Hermes CLI help test against the real Hermes venv); 87 node tests at 100%;
evidence-check `ok`; 2 gate self-tests passed.
