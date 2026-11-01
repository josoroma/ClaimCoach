# Test Report: US-9.2 Redacted Case Summary Tool

Change: us-9-2-case-summary-tool
Story: US-9.2
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24)

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Summary accepts only a case ID: Then the only accepted parameter is a case ID" | PASS | `test_us_9_2_summary_accepts_only_case_id` passed. It checks that the properties are exactly `{case_id}`, `required == ["case_id"]`, `additionalProperties: false`, the pattern `^[A-Za-z0-9_-]{1,64}$`, and that `CaseSummaryParams` has the single field `case_id`. `test_us_9_2_anything_but_a_case_id_is_refused` (5 cases) also passed. Each case answered `invalid_request` with no PHI echoed. Operator run: `make agent-tools` printed the `claimcoach_case_summary` parameters `{"additionalProperties": false, ... "properties": {"case_id": {... "pattern": "^[A-Za-z0-9_-]{1,64}$" ...}}, "required": ["case_id"], "title": "CaseSummaryParams"}`. Live calls with an extra `text` field holding PHI, with a patient name as `case_id`, and with an extra `profile` key each answered `invalid_request`. None echoed its input |
| 2 | "Summary is redacted: Then the returned JSON contains codes, payer name, and status and none of the seeded PHI strings" | PASS | `test_us_9_2_summary_redacted` passed. Related tests also passed: `test_us_9_2_printed_payer_never_returned`, `test_us_9_2_summary_stages`, `test_us_9_2_a_drafted_case`, `test_us_9_2_summary_is_audited`, `test_us_9_2_other_profiles_case_not_found`, `test_us_9_2_summary_through_the_worker`, and `test_us_9_2_the_sessions_profile_reaches_the_worker`. Operator run: I built case `case_b082bd179cc841af` with `make case-new`, then `case-paste` of the synthetic 835 (456 bytes) and of `tests/fixtures/phi` document 0 (409 bytes). I ran `case-process`, confirmed `claim_id` as the member ID `FUD895272471`, and ran `case-diagnose` (`prior_authorization`, `high`). `make agent-call TOOL=claimcoach_case_summary` printed `"ok": true` and exited 0. The answer had `status: "open"`, `stage: "diagnosed"`, `payer: "ACME Health"`, and `codes: ["CO-197", "N286"]`, and it validated as `CaseSummaryResult`. I scanned it for all 10 seeded PHI strings. There were no whole-word hits, no substring hits in any case, and no digit-only hits. The 835's own claim numbers, names, dates, amount, and procedure were also absent. A second case, whose `payer_name` was confirmed as `Avery Vandermeer`, summarized with `payer: null` and also had no PHI hits. `make corpus-audit CASE=<id>` showed a `case_summarized` entry for each summary (2 for 2 calls on case A, 1 on case B) |

## Evidence Commands

```bash
make evidence STORY=US-9.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_9_1 or us_9_2" -v
# operator run against a scratch worker (serve_agent_worker.py in the scratchpad: real create_app,
# CorpusService with InMemoryKeyProvider over a fake embedding server, Redactor over a fake PHI
# model that knows tests/fixtures/phi, fake extraction/classification/explanation models; the
# synthetic CODE_BUNDLE and RULE_BUNDLE imported at start; token + WorkerHandle written where the
# launcher records them)
PYTHONPATH=<repo> HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models \
  .venv/bin/python -W ignore <scratch>/bin/serve_agent_worker.py 18215 -m claimcoach.worker &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18215
# era.835 = ERA_835 of tests/test_us_5_1_case_intake.py; phi_letter.txt = PHI_DOCUMENTS[0]["text"]
make agent-tools
make case-new                                                    # A=case_b082bd179cc841af
make case-paste CASE=$A FILE=<scratch>/data/era.835
make case-paste CASE=$A FILE=<scratch>/data/phi_letter.txt
make case-process CASE=$A
make case-confirm CASE=$A FIELD=claim_id VALUE=FUD895272471
make case-diagnose CASE=$A
make case-show CASE=$A
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$A'"}' > summary.json
PYTHONPATH=<repo> uv run python <scratch>/bin/scan_92.py <scratch>/data     # PHI scan
make corpus-audit CASE=$A
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$A'", "text": "Avery Vandermeer FUD895272471"}'
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "Avery Vandermeer"}'
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$A'", "profile": "other"}'
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "case_0000000000000000"}'
# case B: same documents, claim_id and payer_name (= the patient's name) confirmed
make case-new; make case-paste ... ; make case-process; make case-confirm CASE=$B FIELD=payer_name VALUE="Avery Vandermeer"; make case-diagnose CASE=$B
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$B'"}' > summary_b.json
# case C in profile clinic2, summarized from the default profile
make case-new PROFILE=clinic2; make case-paste CASE=$C FILE=<scratch>/data/phi_letter.txt PROFILE=clinic2
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$C'"}'
make corpus-audit CASE=$B; make corpus-audit CASE=$C PROFILE=clinic2
make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "'$A'"}'; make corpus-audit CASE=$A   # second summary
kill -TERM <worker pid>; lsof -nP -iTCP:18215 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-9.2
tests/test_us_9_2_case_summary.py ..............                         [100%]
- generated xml file: .../evidence/US-9.2/junit.xml -
===================== 14 passed, 1392 deselected in 7.27s ======================

$ uv run pytest ... -k "us_9_1 or us_9_2" -v     (62 passed; the 14 US-9.2 tests:)
test_us_9_2_summary_accepts_only_case_id PASSED
test_us_9_2_anything_but_a_case_id_is_refused[args0..4] PASSED
test_us_9_2_summary_redacted PASSED
test_us_9_2_printed_payer_never_returned PASSED
test_us_9_2_summary_stages PASSED
test_us_9_2_a_drafted_case PASSED
test_us_9_2_summary_is_audited PASSED
test_us_9_2_other_profiles_case_not_found PASSED
test_us_9_2_summary_through_the_worker PASSED
test_us_9_2_the_sessions_profile_reaches_the_worker PASSED

--- operator run (scratch worker, 127.0.0.1:18215) ---
$ make agent-tools
claimcoach_case_summary  (toolset claimcoach, result CaseSummaryResult)
  Return a redacted summary of a ClaimCoach case by case ID: its status, stage, codes, payer (as the rule cards name it), denial reason, and appeal likelihood. No case text or PHI.
  parameters: {"additionalProperties": false, "description": "Arguments of ``claimcoach_case_summary``; a case ID only, never case content (BR-3).", "properties": {"case_id": {"description": "ClaimCoach case ID.", "pattern": "^[A-Za-z0-9_-]{1,64}$", "title": "Case Id", "type": "string"}}, "required": ["case_id"], "title": "CaseSummaryParams", "type": "object"}

case A = case_b082bd179cc841af
case-show documents: edi_835 size_bytes 456; text size_bytes 409  (= era.835, phi_letter.txt)
claim_id {'value': 'FUD895272471', 'status': 'confirmed'}; payer_name {'value': 'ACME HEALTH PLAN', 'status': 'extracted'}
diagnosis {'denial_reason': 'prior_authorization', 'appeal_likelihood': 'high'} stale False

$ make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "case_b082bd179cc841af"}'   (exit 0)
{
  "ok": true,
  "case_id": "case_b082bd179cc841af",
  "status": "open",
  "stage": "diagnosed",
  "outcome": null,
  "payer": "ACME Health",
  "codes": [
    "CO-197",
    "N286"
  ],
  "denial_reason": "prior_authorization",
  "appeal_likelihood": "high",
  "diagnosis_stale": false,
  "deadline": "no_appeal_limit",
  "documents": 2,
  "needs_confirmation": 0
}

$ scan_92.py
seeded PHI strings: 10 ['Avery Vandermeer', 'VANDERMEER, AVERY', 'Avery', 'Vandermeer', '07/05/1954', '9979369', 'FUD895272471', '133-94-1993', '2247 Juniper Hollow Road, Port Ellery, OR 80210', '(950) 555-0157']
case-show (the stored case) holds: ['FUD895272471']
CaseSummaryResult valid; status open stage diagnosed payer ACME Health codes ['CO-197', 'N286']
summary bytes 366
whole-word PHI hits []
substring PHI hits (any case) []
digit-only PHI hits []
case text hits (835 claim numbers/names/dates/amount/procedure) []
keys ['appeal_likelihood', 'case_id', 'codes', 'deadline', 'denial_reason', 'diagnosis_stale', 'documents', 'needs_confirmation', 'ok', 'outcome', 'payer', 'stage', 'status']

$ make corpus-audit CASE=case_b082bd179cc841af
    {"seq": 8, "action": "case_opened",     "case_id": "case_b082bd179cc841af", "profile": "default"},   (the make case-show)
    {"seq": 9, "action": "case_summarized", "case_id": "case_b082bd179cc841af", "profile": "default"}

summary + text field (PHI)    -> "code": "invalid_request", "The request did not match the expected parameters."
case_id "Avery Vandermeer"    -> "code": "invalid_request"
summary + profile key         -> "code": "invalid_request"
case_0000000000000000         -> "code": "case_not_found", "No such case in this profile."
  (each: make: *** [agent-call] Error 1; shell exit 2; no argument echoed)

case B = case_a5659be07af7acef; payer_name {'value': 'Avery Vandermeer', 'status': 'confirmed'}
$ make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "case_a5659be07af7acef"}'   (exit 0)
  "status": "open", "stage": "diagnosed", "payer": null, "codes": ["CO-197", "N286"],
  "denial_reason": "prior_authorization", "appeal_likelihood": "high", "deadline": "no_rule_card", "documents": 2
summary.json   valid; payer ACME Health | whole-word [] | substring [] | case text []
summary_b.json valid; payer None        | whole-word [] | substring [] | case text []

case C = case_b23c2575c2d0a8f8 (profile clinic2), summarized from the default profile:
    "code": "case_not_found", "message": "No such case in this profile."

B audit actions: ['case_created', 'document_added', 'document_added', 'case_extracted', 'field_confirmed', 'field_confirmed', 'case_diagnosed', 'case_diagnosed', 'case_summarized']
C (clinic2) audit actions: ['case_created', 'document_added']                 (no case_summarized)
second summary of A -> ok True diagnosed ACME Health; A case_summarized count: 2

after SIGTERM: worker 18619 exited; lsof rc=1 (nothing listening on 18215); no serve_agent_worker process
```

Artifacts: `evidence/US-9.2/junit.xml`

## Failures

None.

## Notes

- `<scratch>` is
  `/private/tmp/claude-501/-Users-josoroma--claude-spares-spare-i9ct8L/90cb4ea0-d570-4856-9f3d-2969046d7edd/scratchpad/tester-a`,
  and `<repo>` is `/Users/josoroma/sites/ycombinator/claimcoach`.
- The scratch worker and its isolation are described in `evidence/US-9.1/test-report.md`. It is
  the same run: the real `create_app` on 127.0.0.1:18215, a scratch `HERMES_HOME` and
  `MODELS_HOME`, an `InMemoryKeyProvider`, fake model servers, and a token plus `WorkerHandle`
  written where `port_client` reads them. It was started with the ignored trailing words `-m
  claimcoach.worker` so the launcher's `ps` check recognizes it. After SIGTERM, port 18215 was
  free. The scratch token and handle were deleted by hand, because uvicorn re-raises SIGTERM and
  skipped the script's `finally`. The real `~/.hermes` was not touched (its `plugin-data/claimcoach`
  was last modified at 09:32, before this run). No model was downloaded. All data was synthetic:
  `ERA_835` of `tests/test_us_5_1_case_intake.py` and `PHI_DOCUMENTS[0]` of `tests/fixtures/phi`.
- What "seeded PHI" means here: the stored case holds the 409-byte PHI letter as a source
  document (`size_bytes` 409 in `case-show`) and the confirmed member ID `FUD895272471`. The
  worker keeps document text encrypted, and `case-show` lists only document metadata, so only the
  confirmed member ID appears in the `case-show` output. The scan covered every seeded string of
  document 0 (name in four forms, DOB, MRN, member ID, SSN, address, phone).
- The spec-delta scenario "Another profile's case is not found" (in
  `openspec/changes/us-9-2-case-summary-tool/specs/agent-case-summary/spec.md`: "WHEN the agent
  calls claimcoach_case_summary with a case ID of another profile / THEN the tool returns the
  case_not_found envelope") is PASS. `test_us_9_2_other_profiles_case_not_found` passed. In the
  operator run, case C of profile `clinic2`, summarized from the default profile, answered
  `case_not_found`, and no `case_summarized` entry was written for it.
- Out of scope, for the record: one `make case-diagnose` writes two `case_diagnosed` audit entries.
  `Diagnoser` calls `CaseService.save_diagnosis` once after classifying and once after
  explaining. This is EPIC-6 behavior and does not affect these criteria.
- Exit codes: a refused call exits 1 from the CLI, and `make` then returns 2. This matches the
  other `make` targets.
- A live Hermes chat session, where a cloud or local chat model calls the tool, was not run. The
  tool was called through the same guarded handler Hermes registers (via `make agent-call`), and
  `make agent-probe` (5 passed) loaded the plugin into the installed Hermes Agent with a throwaway
  home.
