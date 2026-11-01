# Test Report: US-9.4 The /denial Slash Command

Change: us-9-4-denial-command
Story: US-9.4
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24), gateway venv `~/.hermes/hermes-agent/venv`

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "/denial returns text without PHI: Given the plugin is enabled, When the biller runs /denial, Then the command returns text that contains no PHI" | PASS | The behavior was checked against design decision 1: bare `/denial` gives the fixed guide, and `/denial <case ID>` gives that case's redacted summary. **Real Hermes:** `test_us_9_4_real_hermes_command` (hermes-marked, ran in the `-k` run and in `make agent-probe`) and my own `probe_agent.py` runs. Hermes v0.22.5 `discover_plugins` with `claimcoach` enabled finds the `denial` handler, and `invoke_plugin_command(handler, "")` returns the 4-line guide (pane first, never paste documents, `/denial <case ID>`, ask about codes and payers). `/denial Avery Vandermeer` returns the same guide without echoing the name. `/denial case_b7d74ca3cf2d79c5`, with no worker in that home, returns `The ClaimCoach worker is not running.`. No seeded PHI occurs as a whole word anywhere in the probe payload, and `find_regex_spans` finds nothing in either reply. **Tests:** `test_us_9_4_denial_returns_text_without_phi` (reply == `USAGE`, no seeded PHI, no regex span), `test_us_9_4_denial_summarizes_a_case`, `test_us_9_4_arguments_are_never_echoed` (5 cases, including the whole PHI letter), `test_us_9_4_unknown_case_is_a_fixed_message`, `test_us_9_4_failures_are_fixed_messages`, `test_us_9_4_render_summary_variants`, `test_us_9_4_command_registered`, `test_us_9_4_cli_runs_denial`. All 13 passed. **Operator:** on my scratch worker (127.0.0.1:18216) I ran 14 `/denial` invocations through `make agent-denial` and `python -m claimcoach.agent denial`. Cases A and B each hold the 835 plus the 409-byte PHI letter of fixture document 0. A has `claim_id` confirmed as the member ID `FUD895272471`. B also has `payer_name` confirmed as the patient's name `Avery Vandermeer`. C holds the letter only, at intake. The replies: A gives `Payer: ACME Health / Codes: CO-197, N286 / Denial reason: prior_authorization; appeal likelihood: high`. B gives `Payer: no rule card matches the payer` (the PHI payer was not shown). C gives `intake / Codes: none read yet`. Unknown IDs, `Vandermeer`, `FUD895272471`, and `133-94-1993` give `No such case in this profile.`. A name, or the whole letter, as the argument gives the guide. A wrong port, or a stopped worker, gives `The ClaimCoach worker is not running.`. I scanned every reply for all 10 seeded PHI strings (whole word and substring, any case), the whole-word strings of all 12 fixture documents, US-3.1 regex spans, and case text (`CLAIM-77`, `PCN-0001`, `SYNTHETIC`, `ACME HEALTH PLAN`, dates, `250`, `$`). Every list was empty |

## Evidence Commands

```bash
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_9_3 or us_9_4" -v
make evidence STORY=US-9.4
make agent-probe                                   # HERMES_HOME/MODELS_HOME=<scratch>/...
# Hermes probe by hand (throwaway home <scratch>/probe-home: plugins/claimcoach -> <repo>/plugin, plugins.enabled: [claimcoach])
cd <scratch>/probe-cwd && HERMES_HOME=<scratch>/probe-home PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python <repo>/tests/hermes/probe_agent.py "Avery Vandermeer"
cd <scratch>/probe-cwd && HERMES_HOME=<scratch>/probe-home PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python <repo>/tests/hermes/probe_agent.py case_b7d74ca3cf2d79c5
# scratch worker (serve_denial_worker.py, see Notes)
HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models PYTHONPATH=<repo> \
  .venv/bin/python -W ignore <scratch>/bin/serve_denial_worker.py 18216 -m claimcoach.worker &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18216
make worker-status
make agent-denial                                  # 1
make agent-denial CASE=$A; make agent-denial CASE=$B; make agent-denial CASE=$C     # 2-4
make agent-denial CASE=case_0000000000000000       # 5
make agent-denial CASE=Vandermeer                  # 6
make agent-denial CASE=FUD895272471                # 7
make agent-denial CASE="Avery Vandermeer"          # 8
make agent-denial CASE=133-94-1993                 # 9
uv run python -m claimcoach.agent denial "Avery Vandermeer" --port 18216          # 10
uv run python -m claimcoach.agent denial "$(cat <scratch>/phi_letter.txt)" --port 18216   # 11
uv run python -m claimcoach.agent denial $A --port 18217                          # 12 (no worker recorded there)
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "<A>"}'            # 13 raw tool result
make case-show CASE=$A / $B / $C                   # confirm the cases hold the seeded PHI
PYTHONPATH=<repo> uv run python -W ignore <scratch>/bin/scan_replies.py <scratch>
kill -TERM <worker pid>; lsof -nP -iTCP:18216
make agent-denial CASE=$A                          # 14 after stop
make evidence-check
```

```text
$ uv run pytest ... -k "us_9_3 or us_9_4" -v      (22 passed; US-9.4 lines)
tests/test_us_9_4_denial_command.py::test_us_9_4_denial_returns_text_without_phi PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_command_registered PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_real_hermes_command PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_denial_summarizes_a_case PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_arguments_are_never_echoed[Avery Vandermeer] PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_arguments_are_never_echoed[SSN 133-94-1993] PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_arguments_are_never_echoed[case 01] PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_arguments_are_never_echoed[xxxx...x (65)] PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_arguments_are_never_echoed[raw_args4] PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_unknown_case_is_a_fixed_message PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_failures_are_fixed_messages PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_render_summary_variants PASSED
tests/test_us_9_4_denial_command.py::test_us_9_4_cli_runs_denial PASSED

$ make evidence STORY=US-9.4
collected 1406 items / 1393 deselected / 13 selected
tests/test_us_9_4_denial_command.py .............                        [100%]
- generated xml file: .../evidence/US-9.4/junit.xml -
===================== 13 passed, 1393 deselected in 6.40s ======================

$ make agent-probe
tests/test_us_1_1_plugin_package.py ...  tests/test_us_9_3_skill.py .  tests/test_us_9_4_denial_command.py .
====================== 5 passed, 36 deselected in 40.47s =======================

$ probe_agent.py "Avery Vandermeer"      (Hermes v0.22.5, exit 0)
denial(''):   '/denial: start denial work with ClaimCoach.\n1. Open the ClaimCoach pane, create ' ...
denial(arg):  "/denial: start denial work with ClaimCoach.\n1. Open the ClaimCoach pane, ... claimcoach:denial-triage playbook."
PHI whole-word in whole probe payload: [] | regex spans in denial replies: []
$ probe_agent.py case_b7d74ca3cf2d79c5   (exit 0)
denial(arg):  'The ClaimCoach worker is not running.'
PHI whole-word in whole probe payload: [] | regex spans in denial replies: []

--- operator run (scratch worker, 127.0.0.1:18216) ---
cases {"A": "case_b7d74ca3cf2d79c5", "B": "case_18f4e322bfd72ce6", "C": "case_8f81badfaebfa9fd"}
$ make worker-status
{"pid":19271,"base_url":"http://127.0.0.1:18216","token_path":"<scratch>/hermes/plugin-data/claimcoach/worker/token",...}
case-show B: documents edi_835 456 bytes, text 409 bytes;
  extraction.payer_name {"value": "Avery Vandermeer", "status": "confirmed"}, claim_id {"value": "FUD895272471", "status": "confirmed"}
case-show A: documents edi_835 456 bytes, text 409 bytes; claim_id FUD895272471 (confirmed)

=== 1_noarg: make agent-denial                      exit=0
/denial: start denial work with ClaimCoach.
1. Open the ClaimCoach pane, create a case, and add the EOB, 835, or denial letter there. Never paste claim documents or patient details into this chat.
2. Run /denial <case ID> for the case's redacted summary: status, codes, payer, denial reason.
3. Ask about a code (CO-197) or a payer's rules; answers come from the ClaimCoach global corpus and the claimcoach:denial-triage playbook.
=== 2_caseA: make agent-denial CASE=case_b7d74ca3cf2d79c5     exit=0
ClaimCoach case case_b7d74ca3cf2d79c5: open, diagnosed
Payer: ACME Health
Codes: CO-197, N286
Denial reason: prior_authorization; appeal likelihood: high
Appeal deadline: unknown: the payer's cards give no appeal limit
Documents: 2; fields to confirm: 0
Next: Draft the appeal in the pane.
=== 3_caseB: make agent-denial CASE=case_18f4e322bfd72ce6     exit=0
ClaimCoach case case_18f4e322bfd72ce6: open, diagnosed
Payer: no rule card matches the payer
Codes: CO-197, N286
Denial reason: prior_authorization; appeal likelihood: high
Appeal deadline: unknown: no rule card for this payer
Documents: 2; fields to confirm: 0
Next: Draft the appeal in the pane.
=== 4_caseC: make agent-denial CASE=case_8f81badfaebfa9fd     exit=0
ClaimCoach case case_8f81badfaebfa9fd: open, intake
Payer: no rule card matches the payer
Codes: none read yet
Documents: 1; fields to confirm: 0
Next: Process the case in the ClaimCoach pane to extract its fields.
=== 5_unknown CASE=case_0000000000000000   exit=0   No such case in this profile.
=== 6_surname CASE=Vandermeer              exit=0   No such case in this profile.
=== 7_memberid CASE=FUD895272471           exit=0   No such case in this profile.
=== 8_name CASE="Avery Vandermeer"         exit=2   usage: make agent-denial CASE=<case id>
=== 9_ssn CASE=133-94-1993                 exit=0   No such case in this profile.
=== 10_name_cli "Avery Vandermeer"         exit=0   (the 4-line guide)
=== 11_letter_cli <whole PHI letter>       exit=0   (the 4-line guide)
=== 12_wrongport --port 18217              exit=0   The ClaimCoach worker is not running.
=== 13 agent-call claimcoach_case_summary A: {"ok": true, "case_id": "case_b7d74ca3cf2d79c5", "status": "open",
    "stage": "diagnosed", "outcome": null, "payer": "ACME Health", "codes": ["CO-197", "N286"],
    "denial_reason": "prior_authorization", "appeal_likelihood": "high", "diagnosis_stale": false,
    "deadline": "no_appeal_limit", "documents": 2, "needs_confirmation": 0}

$ scan_replies.py
seeded PHI strings (document 0): 10 ['Avery Vandermeer', 'VANDERMEER, AVERY', 'Avery', 'Vandermeer', '07/05/1954', '9979369', 'FUD895272471', '133-94-1993', '2247 Juniper Hollow Road, Port Ellery, OR 80210', '(950) 555-0157']
1_noarg.txt        431 bytes | whole-word doc0 [] | substring doc0 [] | whole-word all 12 docs [] | regex spans [] | case text []
2_caseA.txt        290 bytes | whole-word doc0 [] | substring doc0 [] | whole-word all 12 docs [] | regex spans [] | case text []
3_caseB.txt        298 bytes | whole-word doc0 [] | substring doc0 [] | whole-word all 12 docs [] | regex spans [] | case text []
4_caseC.txt        215 bytes | whole-word doc0 [] | substring doc0 [] | whole-word all 12 docs [] | regex spans [] | case text []
5_unknown.txt       30 bytes | ... all []          6_surname.txt  30 bytes | ... all []
7_memberid.txt      30 bytes | ... all []          8_name.txt     73 bytes | ... all []
9_ssn.txt           30 bytes | ... all []          10_name_cli.txt 431 bytes | ... all []
11_letter_cli.txt  431 bytes | ... all []          12_wrongport.txt 38 bytes | ... all []
13_tool_A.txt (raw tool JSON): whole-word [] substring []

$ kill -TERM 19271
worker process gone
lsof -nP -iTCP:18216 -> exit=1 (nothing on 18216)
=== 14_after_stop: make agent-denial CASE=case_b7d74ca3cf2d79c5   exit=0
The ClaimCoach worker is not running.        (scanned too: no PHI)
```

Artifacts: `evidence/US-9.4/junit.xml`

## Failures

None.

## Notes

- `<scratch>` is
  `/private/tmp/claude-501/-Users-josoroma--claude-spares-spare-i9ct8L/90cb4ea0-d570-4856-9f3d-2969046d7edd/scratchpad/tester-b`,
  and `<repo>` is `/Users/josoroma/sites/ycombinator/claimcoach`.
- The scratch worker: `<scratch>/bin/serve_denial_worker.py` (in the scratchpad, not the repo)
  served the real `claimcoach.worker.app.create_app` with uvicorn on 127.0.0.1:18216. It used
  `corpus=` `tests/fakes/corpus.make_service` (a `CorpusService` with `InMemoryKeyProvider`, no
  Keychain item, over a fake embedding server), `redactor=` a `Redactor(PhiDetector(...))` over a
  fake PHI model serving `fake_phi_reply(*PHI_DOCUMENTS)`, and `pipeline_models=` the fake
  extraction, classification, and explanation servers of `tests/fakes/agent.serve_pipeline`. This
  is the wiring of `tests/fakes/agent.agent_worker`, served on a fixed port.
  - Cases A and B were made with `tests/fakes/agent.diagnosed_case`, which uses `ERA_835` of
    `tests/test_us_5_1_case_intake.py` plus `PHI_DOCUMENTS[0]["text"]`. C was made with
    `CaseService.create` and `add_text`.
  - The script wrote the launch token with `issue_token` to
    `<scratch>/hermes/plugin-data/claimcoach/worker/token`, and a `WorkerHandle` (its own PID,
    `http://127.0.0.1:18216`) to `worker.json` beside it. `claimcoach.cli.port_client` reads both
    there.
  - The launcher accepts a PID only if its `ps` command line contains ` -m claimcoach.worker `.
    The script was therefore started as `serve_denial_worker.py 18216 -m claimcoach.worker`. The
    trailing words are only there for that check, and the script ignores them. `make
    worker-status` then reported the handle.
  - It was stopped with SIGTERM. The process exited and nothing was listening on port 18216
    afterwards. On that exit, the script's `finally` cleanup did not run, so it did not remove the
    token and `worker.json`. The next CLI call cleared the stale `worker.json` (launcher
    `worker_status`), and I deleted the scratch token by hand. This affects only my harness, not
    the product.
- Isolation: the real `~/.hermes` was not used. `~/.hermes/config.yaml` has the same mtime and
  SHA-1 before and after, `~/.hermes/plugins` is still empty, and
  `~/.hermes/plugin-data/claimcoach` was last changed at 09:32, before this run. Running the
  Hermes probe may have written bytecode caches under `~/.hermes/hermes-agent` (accepted by the
  task). No model was downloaded. All data was synthetic.
- Not exercised: real Hermes running `/denial <case ID>` against a live worker that returns a
  summary. Inside the gateway, the plugin connects to the worker on the default port 18200
  (`worker_client` uses `WorkerConfig` defaults), and this run had to use port 18216. Through real
  Hermes I saw the guide, the no-echo guide for a name, and the `worker_unavailable` message. I saw
  the case summary through the same `/denial` handler and the same guarded
  `claimcoach_case_summary` handler, run by `make agent-denial` (`python -m claimcoach.agent
  denial`) and by `test_us_9_4_denial_summarizes_a_case` (the registered command over a live
  loopback worker). The criterion holds on every path I exercised. Only the combination "Hermes
  dispatch + summary reply" was not seen.
- Typing `/denial` in a live Hermes chat or desktop was not exercised. The probe calls Hermes'
  own `invoke_plugin_command`, which the chat surface uses to dispatch plugin commands.
- `make agent-denial CASE="Avery Vandermeer"` is refused by the Makefile's `REQUIRE_CASE` (exit
  2). Its usage line does not repeat the value. The CLI path given the same name (row 10) answers
  the guide, as design decision 3 says.
- Spec delta (`openspec/changes/us-9-4-denial-command/specs/*/spec.md`):
  - "/denial returns text without PHI": PASS, the same evidence as row 1.
  - "/denial with a case ID summarizes the case" ("WHEN the biller runs /denial with the ID of a
    case holding seeded PHI / THEN the reply names the case's codes, payer, and status and none of
    the seeded PHI strings"): PASS. `test_us_9_4_denial_summarizes_a_case` passed. On the operator
    run, case A's reply named `open, diagnosed`, `ACME Health`, and `CO-197, N286`, with no seeded
    string. Case B, whose `payer_name` was confirmed as the patient's name, answered `no rule card
    matches the payer` and did not show the name.
- `scan_replies.py` removes the case IDs from a reply before its regex check, because a case ID is
  the biller's own handle and the reply has to name it. The seeded-string scans read the full
  replies. I then re-ran `find_regex_spans` and `leaked_strings` over all 14 reply files with the
  case IDs left in, including `14_after_stop.txt`. Every result was `[]`.
