# Test Report: US-9.1 Code and Payer-Rule Tools

Change: us-9-1-code-payer-tools
Story: US-9.1
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24)

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "explain_code answers from the global corpus: Then the tool returns a JSON string validating against the typed ExplainCodeResult with the corpus entry" | PASS | `test_us_9_1_explain_code_from_global` passed. Related tests also passed: `test_us_9_1_explain_code_answers_a_bare_or_remark_code`, `test_us_9_1_code_shapes` (16 cases), `test_us_9_1_unknown_code_is_not_found` (5 cases), `test_us_9_1_zero_padded_codes_are_one_code` (4 cases), `test_us_9_1_reference_text_is_guarded`, `test_us_9_1_schemas_from_params`, `test_us_9_1_tools_through_the_worker`, and `test_us_9_1_cli_calls_a_tool_as_the_agent_does`. Operator run: the scratch worker held the synthetic `CODE_BUNDLE`, and `make corpus-list` showed `GROUP/CO` and `CARC/197`. `make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'` printed `"ok": true` and exited 0. The answer had 2 entries: `GROUP/CO` "Contractual obligation" and `CARC/197` "Precertification absent". Their titles, bodies, sources, and `verified_on` dates match the bundle exactly. The printed JSON validated as `ExplainCodeResult`. `CO-999` gave `code_not_found`, `"Avery Vandermeer"` gave `invalid_request`, and an extra key gave `invalid_request`. None of these echoed its input. With the worker stopped, the call gave `worker_unavailable` |
| 2 | "payer_rules returns the payer's rule card: Then the tool returns a JSON string validating against the typed PayerRulesResult with that card" | PASS | `test_us_9_1_payer_rules_returns_card` passed for `ACME Health`, `ACME HEALTH PLAN`, and `The ACME Health Plan`. `test_us_9_1_unknown_payer_is_not_found` also passed. Operator run: `make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "ACME Health"}'` printed `"ok": true` and exited 0. It returned exactly the 2 `ACME Health` cards (`appeal_levels`, and `required_docs` with its 4 required documents). It did not return the `ACME` card or the `Other Payer` card. The printed JSON validated as `PayerRulesResult`. `Other Payer` returned only its own card. `Nowhere Mutual` and `Avery Vandermeer` gave `payer_not_found` with no echo |

## Evidence Commands

```bash
make evidence STORY=US-9.1
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_9_1 or us_9_2" -v
# operator run against a scratch worker (serve_agent_worker.py in the scratchpad: real create_app,
# CorpusService with InMemoryKeyProvider over a fake embedding server, Redactor over a fake PHI
# model that knows tests/fixtures/phi, fake extraction/classification/explanation models; the
# synthetic CODE_BUNDLE and RULE_BUNDLE of tests/fakes/diagnosis.py imported at start; this
# launch's token and a WorkerHandle written to <scratch>/hermes/plugin-data/claimcoach/worker/)
PYTHONPATH=<repo> HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models \
  .venv/bin/python -W ignore <scratch>/bin/serve_agent_worker.py 18215 -m claimcoach.worker &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18215
make agent-tools
make corpus-list
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'      > explain.json
make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "ACME Health"}' > payer.json
PYTHONPATH=<repo> uv run python <scratch>/bin/validate_91.py <scratch>/data   # model_validate_json + bundle compare
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "N286"}'
make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "Other Payer"}'
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-999"}'
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "Avery Vandermeer"}'
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197", "extra": 1}'
make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "Nowhere Mutual"}'
make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "Avery Vandermeer"}'
kill -TERM <worker pid>; lsof -nP -iTCP:18215 -sTCP:LISTEN
make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'      # worker stopped
env -u HERMES_HOME make agent-probe
```

```text
$ make evidence STORY=US-9.1
tests/test_us_9_1_reference_tools.py ................................... [ 72%]
.............                                                            [100%]
- generated xml file: .../evidence/US-9.1/junit.xml -
===================== 48 passed, 1358 deselected in 13.06s =====================

$ uv run pytest ... -k "us_9_1 or us_9_2" -v     (62 passed; the 48 US-9.1 tests:)
test_us_9_1_explain_code_from_global PASSED
test_us_9_1_explain_code_answers_a_bare_or_remark_code PASSED
test_us_9_1_code_shapes[CO-197, co-197, PR-B7, OA-016, 197, N286, MA130, M15, CO, CO-N286, XYZ, 1970, ZZ-197, CO-197-1, CO-, -197] PASSED
test_us_9_1_payer_rules_returns_card[ACME Health] PASSED
test_us_9_1_payer_rules_returns_card[ACME HEALTH PLAN] PASSED
test_us_9_1_payer_rules_returns_card[The ACME Health Plan] PASSED
test_us_9_1_unknown_code_is_not_found[CO-999, 999, N999, XYZ, CR] PASSED
test_us_9_1_unknown_payer_is_not_found PASSED
test_us_9_1_a_reason_code_without_its_group_entry PASSED
test_us_9_1_zero_padded_codes_are_one_code[016-16, 016-CO-016, 16-016, 7-007] PASSED
test_us_9_1_long_reference_text_is_cut PASSED
test_us_9_1_reference_text_is_guarded PASSED
test_us_9_1_schemas_from_params PASSED
test_us_9_1_bad_arguments_are_invalid_requests[args0..4] PASSED
test_us_9_1_handler_failures_are_envelopes PASSED
test_us_9_1_handlers_are_bound_at_registration PASSED
test_us_9_1_tools_through_the_worker PASSED
test_us_9_1_cli_lists_the_tools_offline PASSED
test_us_9_1_cli_calls_a_tool_as_the_agent_does PASSED
test_us_9_1_cli_refuses_bad_args_without_echoing[Avery Vandermeer-error: --args is not JSON] PASSED
test_us_9_1_cli_refuses_bad_args_without_echoing[["CO-197"]-error: --args is not a JSON object] PASSED
test_us_9_1_cli_ports_stay_in_range PASSED

--- operator run (scratch worker, 127.0.0.1:18215) ---
$ make agent-tools        (exit 0)
claimcoach_explain_code  (toolset claimcoach, result ExplainCodeResult)
  parameters: {"additionalProperties": false, ... "properties": {"code": {... "maxLength": 16, "minLength": 1, "pattern": "^[A-Za-z0-9-]+$" ...}}, "required": ["code"], "title": "ExplainCodeParams", "type": "object"}
claimcoach_payer_rules  (toolset claimcoach, result PayerRulesResult)
  parameters: {"additionalProperties": false, ... "properties": {"payer": {... "maxLength": 120, "minLength": 1 ...}}, "required": ["payer"], "title": "PayerRulesParams", "type": "object"}
claimcoach_case_summary  (toolset claimcoach, result CaseSummaryResult)
skill: claimcoach:denial-triage  (.../plugin/skills/denial-triage/SKILL.md)
command: /denial [case ID]

$ make corpus-list
code             CARC/18                          2026-09-01       Synthetic code list for tests
code             CARC/197                         2026-09-01       Synthetic code list for tests
code             GROUP/CO                         2026-09-01       Synthetic code list for tests
code             RARC/N286                        2026-09-01       Synthetic code list for tests
rule_card        ACME Health/appeal_levels        2026-10-01       ACME Health provider manual (synthetic)
rule_card        ACME Health/required_docs        2026-10-01       ACME Health provider manual (synthetic) (4 required documents)
rule_card        ACME/required_docs               2026-10-01       ACME provider manual (synthetic) (1 required documents)
rule_card        Other Payer/required_docs        2026-10-01       Other Payer provider manual (synthetic) (1 required documents)

$ make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'     (exit 0)
{
  "ok": true,
  "code": "CO-197",
  "entries": [
    {"code_set": "GROUP", "code": "CO", "title": "Contractual obligation",
     "explanation": "The provider may not bill the patient.", "truncated": false,
     "source": "Synthetic code list for tests", "verified_on": "2026-09-01", "stale": false},
    {"code_set": "CARC", "code": "197", "title": "Precertification absent",
     "explanation": "Authorization was not obtained.", "truncated": false,
     "source": "Synthetic code list for tests", "verified_on": "2026-09-01", "stale": false}
  ]
}

$ make agent-call TOOL=claimcoach_payer_rules ARGS='{"payer": "ACME Health"}'  (exit 0)
{
  "ok": true,
  "payer": "ACME Health",
  "cards": [
    {"payer": "ACME Health", "topic": "appeal_levels", "title": "ACME Health appeal levels",
     "body": "Synthetic appeal levels rule for ACME Health.", "truncated": false,
     "required_documents": [], "appeal_limit_days": null,
     "source": "ACME Health provider manual (synthetic)", "verified_on": "2026-10-01", "stale": false},
    {"payer": "ACME Health", "topic": "required_docs", "title": "ACME Health required docs",
     "body": "Synthetic required docs rule for ACME Health.", "truncated": false,
     "required_documents": ["Copy of the denial notice or remittance",
       "Prior authorization number or retro-authorization request",
       "Medical records for the date of service", "Signed appeal form"],
     "appeal_limit_days": null, "source": "ACME Health provider manual (synthetic)",
     "verified_on": "2026-10-01", "stale": false}
  ]
}

$ validate_91.py
ExplainCodeResult valid: ExplainCodeResult code CO-197 entries [('GROUP', 'CO'), ('CARC', '197')]
PayerRulesResult valid: PayerRulesResult payer ACME Health cards [('ACME Health', 'appeal_levels'), ('ACME Health', 'required_docs')]
CODE_BUNDLE: CodeEntry(title='Precertification absent', body='Authorization was not obtained.', source='Synthetic code list for tests', verified_on=2026-09-01, code_set='CARC', code='197'),
             CodeEntry(title='Contractual obligation', body='The provider may not bill the patient.', ..., code_set='GROUP', code='CO')   -> identical to the answer
RULE_BUNDLE: RuleCard(title='ACME Health required docs', ..., required_documents=[the same 4]), RuleCard(title='ACME Health appeal levels', ...)  -> identical to the answer

explain N286           -> True N286 [('RARC', 'N286', 'Referring provider identifier')]
payer Other Payer      -> True Other Payer [('Other Payer', 'required_docs', ["Another payer's form"])]
explain CO-999         -> "code": "code_not_found",  "That code is not in the ClaimCoach global corpus."
explain Avery Vandermeer -> "code": "invalid_request", "The request did not match the expected parameters."
explain CO-197 + extra -> "code": "invalid_request"
payer Nowhere Mutual   -> "code": "payer_not_found", "The ClaimCoach global corpus has no rule cards for that payer."
payer Avery Vandermeer -> "code": "payer_not_found"
  (each refusal: make: *** [agent-call] Error 1; shell exit 2; no argument echoed)

after SIGTERM: worker 18619 exited; lsof rc=1 (nothing listening on 18215); no serve_agent_worker process
$ make agent-call TOOL=claimcoach_explain_code ARGS='{"code": "CO-197"}'      (worker stopped)
    "code": "worker_unavailable",
    "message": "The ClaimCoach worker is not running."

$ make agent-probe     (throwaway HERMES_HOME per test)
tests/test_us_1_1_plugin_package.py ...                                  [ 60%]
tests/test_us_9_3_skill.py .                                             [ 80%]
tests/test_us_9_4_denial_command.py .                                    [100%]
======================= 5 passed, 36 deselected in 4.68s =======================
```

Artifacts: `evidence/US-9.1/junit.xml`

## Failures

None.

## Notes

- `<scratch>` is
  `/private/tmp/claude-501/-Users-josoroma--claude-spares-spare-i9ct8L/90cb4ea0-d570-4856-9f3d-2969046d7edd/scratchpad/tester-a`,
  and `<repo>` is `/Users/josoroma/sites/ycombinator/claimcoach`.
- How the operator run was isolated: `serve_agent_worker.py` (in the scratchpad, not the repo)
  served the real `claimcoach.worker.app.create_app` on 127.0.0.1:18215. It used a scratch
  `HERMES_HOME` and `MODELS_HOME`, an `InMemoryKeyProvider` (no Keychain item), and in-process
  `FakeModelServer`s. `make agent-call` reaches the worker through `port_client`, which sends the
  token only to the worker the launcher recorded. So the script wrote this launch's token to
  `<scratch>/hermes/plugin-data/claimcoach/worker/token` (mode 0600) and a `WorkerHandle` with its
  own PID to `worker.json` next to it. It was started with the trailing words `-m
  claimcoach.worker`, which the script ignores, so that the launcher's `_is_worker` check (`ps`
  command line) recognizes it. No source code was changed.
- After SIGTERM the worker exited, and port 18215 was free. The script's `finally` block did not
  run, because uvicorn re-raises SIGTERM after shutdown. I deleted the scratch token and
  `worker.json` by hand. This is about the harness only, not the product.
- The real `~/.hermes` was not touched. `~/.hermes/plugin-data/claimcoach` was last modified at
  09:32, before this run, and has no `worker` folder. No model was downloaded. All data was
  synthetic.
- The spec-delta scenarios in
  `openspec/changes/us-9-1-code-payer-tools/specs/agent-reference-tools/spec.md` were exercised as
  follows:
  - "An unknown code is not guessed" ("THEN the tool returns the code_not_found envelope"): PASS.
    `test_us_9_1_unknown_code_is_not_found` (5 cases) passed, and the operator call with `CO-999`
    returned `code_not_found`.
  - "No worker running" ("THEN the tool returns the worker_unavailable envelope"): PASS. The
    operator call after the worker stopped returned `worker_unavailable`. I also ran
    `uv run pytest -k test_us_1_1_tools_answer_an_envelope_without_a_worker` separately, and it
    passed (1 passed). That test covers all three tools with no worker token.
- Exit codes: the runbook says a not-found answer "exits 1". The CLI does exit 1 (`make: ***
  [agent-call] Error 1`), and `make` itself then returns 2. This matches the other `make` targets
  (noted in US-7.2 and US-8.3). It is not a defect against these criteria.
- The tools were called through the guarded handler that `make agent-call` runs, which is the
  same handler Hermes registers. `make agent-probe` loaded the plugin into the installed Hermes
  Agent with a throwaway home. A live Hermes chat session, where a model chooses to call these
  tools, was not run. The criteria are about what the tool returns, and that was observed
  directly.
