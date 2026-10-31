# Test Report: US-5.2 Structured Extraction and Field Confirmation

Change: us-5-2-structured-extraction
Story: US-5.2
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; Qwen3-VL-8B weights absent

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Extraction fills the structured case: Then the case holds claim lines with CARC, RARC, and group codes, dates, and amounts that validate against the typed CaseExtraction model" | PASS | Exercised by the offline pipeline, which uses the fake vision model. The real model's reading of the EOB is UNVERIFIED: `test_us_5_2_extraction_fills_case` (marked `models`) was SKIPPED because the Qwen3-VL-8B weights are not at `~/Models/Qwen3-VL-8B-Instruct-4bit`. `test_us_5_2_extraction_fills_case_offline`: a synthetic EOB PDF goes through the real rasterize, prompt, and parse pipeline, against a fake OpenAI-compatible server that replies with the EOB reading. The stored `CaseExtraction` passes `assert_eob_fields`, `needs_confirmation == []`, and `sources` is the PDF. There is one model call: the system prompt is the registered `EXTRACTION_TEMPLATE`, the text layer sits inside the data delimiters, and the page is sent as a PNG `image_url`. `case_extracted` is audited. `test_us_5_2_835_extraction_fills_case`: pasted 835 text gives the same fields with `vision.requests == []`. `test_us_5_2_values_validate_one_by_one[...]` (13 cases). Operator: `make case-process` on a case holding the EOB PDF and the 835 ended `done 100%`. `make case-show` showed line `99213`, `2026-09-01`, billed `250`, paid `0`, adjustment `CO`/`197`/`250`, RARC `N286`, payer `ACME HEALTH PLAN`, claim `CLAIM-77`, all `extracted` |
| 2 | "Unreadable fields are highlighted: Then that field is highlighted for confirmation" | PASS | `test_us_5_2_unreadable_fields_highlighted`: the model reply has no claim number, a date `13/45/2026`, the amount `"two hundred"`, a null paid amount, group code `XX`, and RARC `X1`. The result is `needs_confirmation == ["claim_id", "lines.0.service_date", "lines.0.billed_amount", "lines.0.paid_amount", "lines.0.adjustments.0.group_code", "lines.0.rarc_codes.1"]`, each `unreadable` with no value, while the CARC stays `extracted`. `test_us_5_2_an_unusable_reply_leaves_every_field_unreadable`. Pane (node): `test_us_5_2_pane_unreadable_fields_highlighted` checks that the claim number item has `aria-invalid=true`, an amber outline and background, and the label "Claim number (needs confirmation)". The other items are not highlighted. Operator: with only the EOB PDF attached and a fake model that omits `claim_id`, `make case-show` printed `needs_confirmation: ['claim_id']` and `claim_id: {'value': None, 'status': 'unreadable'}` |
| 3 | "Confirmed fields are stored as confirmed: Then the field is stored with the confirmed value and is no longer highlighted" | PASS | `test_us_5_2_confirmed_fields_stored`: `POST /cases/{id}/fields` `claim_id=" CLAIM-77 "` gives `Extracted(value="CLAIM-77", status=confirmed)`, and `needs_confirmation == []` both in the response and on re-open. `field_confirmed` is audited. A corrected `lines.0.service_date` is stored as confirmed. A re-run keeps both values. `test_us_5_2_invalid_confirmations_change_nothing`: a bad date, an out-of-range line, a CARC `Jane Doe`, the path `../etc`, an empty value, and a bad case ID each get 422 `invalid_request`, the case is unchanged, and the value is not echoed. Pane (node): `test_us_5_2_pane_confirmed_fields_stored`. Operator: `make case-confirm FIELD=claim_id VALUE=CLAIM-77` gave `{'value': 'CLAIM-77', 'status': 'confirmed'}` and `needs_confirmation: []`, and `make case-show` agreed. `VALUE="O'Brien Health"` on `payer_name` was stored verbatim as confirmed. `not-a-date` and CARC `1234` got 422 `invalid_request` and line 0 stayed unchanged. A re-run of `make case-process` kept both confirmed values |
| 4 | "Extraction progress is pushed as events: Then the worker broadcasts a plugin.claimcoach progress event that the pane receives through host.onEvent" | PASS | `test_us_5_2_progress_pushed_as_events`: a 2-page EOB is processed through the gateway router, the gateway relay, and the worker. Every event that reaches the sink is `("claimcoach", "case.progress")`, and its payload validates as `CaseProgressEvent` with the case and job IDs. The stages are `extracting, extracting, extracting, done`, with progress rising from 0.0 to 1.0. No payload contains `ACME`, `CLAIM-77`, `eob.pdf`, or `99213`. Pane (node): `test_us_5_2_pane_receives_progress_events` checks that the pane registers `ctx.onEvent('plugin.claimcoach.case.progress')`. An emitted event for the open case updates the progress to 48%, and events for other cases, events without `job_id`, and events from other plugins are ignored. Also `test_us_5_2_a_failed_job_ends_with_its_code[...]` and `test_us_5_2_event_sink_is_hermes_broadcast`. Operator: `make case-process` printed the worker's events `extracting 0%`, `extracting 48%`, `extracting 95%`, `done 100%` |

## Evidence Commands

```bash
make evidence STORY=US-5.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_5_1 or us_5_2" -v
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_5_2 plugin/desktop/tests/
uv run pytest -m models -k us_5_2 -rs --no-cov -p no:cacheprovider
# operator run against a scratch worker (serve_case_worker.py: real create_app, in-memory key,
# fake vision model whose reply leaves claim_id unreadable)
HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models .venv/bin/python -W ignore serve_case_worker.py --port 18215 &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18215
make case-process CASE=case_63dbde3243b9a0fa          # EOB PDF + pasted 835
make case-show CASE=case_63dbde3243b9a0fa
make case-new; make case-add CASE=case_5c3cd175ef326fad FILE=<scratch>/eob.pdf   # EOB PDF only
make case-process CASE=case_5c3cd175ef326fad
make case-show CASE=case_5c3cd175ef326fad
make case-confirm CASE=case_5c3cd175ef326fad FIELD=claim_id VALUE=CLAIM-77
make case-confirm CASE=case_5c3cd175ef326fad FIELD=payer_name VALUE="O'Brien Health"
make case-confirm CASE=case_5c3cd175ef326fad FIELD=lines.0.service_date VALUE=not-a-date
make case-confirm CASE=case_5c3cd175ef326fad FIELD=lines.0.adjustments.0.carc VALUE=1234
make case-confirm CASE=case_5c3cd175ef326fad FIELD=claim_id
make case-process CASE=case_5c3cd175ef326fad          # re-run after confirmation
make case-process CASE=case_0000000000000000          # unknown case
make case-process CASE=case_f8194e3bbb5fc402          # empty case
```

```text
tests/test_us_5_2_extraction.py ........................................ [ 65%]
.....................                                                    [100%]
- generated xml file: .../evidence/US-5.2/junit.xml -
====================== 61 passed, 920 deselected in 3.45s ======================

test_us_5_2_extraction.py::test_us_5_2_extraction_fills_case_offline PASSED
test_us_5_2_extraction.py::test_us_5_2_835_extraction_fills_case PASSED
test_us_5_2_extraction.py::test_us_5_2_unreadable_fields_highlighted PASSED
test_us_5_2_extraction.py::test_us_5_2_an_unusable_reply_leaves_every_field_unreadable PASSED
test_us_5_2_extraction.py::test_us_5_2_confirmed_fields_stored PASSED
test_us_5_2_extraction.py::test_us_5_2_invalid_confirmations_change_nothing PASSED
test_us_5_2_extraction.py::test_us_5_2_progress_pushed_as_events PASSED
test_us_5_2_extraction.py::test_us_5_2_relay_reports_a_lost_worker PASSED
test_us_5_2_extraction.py::test_us_5_2_relay_stops_at_its_deadline PASSED
test_us_5_2_extraction.py::test_us_5_2_jobs_stop_at_their_deadline PASSED
test_us_5_2_extraction.py::test_us_5_2_null_lists_and_bad_items_keep_the_rest PASSED
test_us_5_2_extraction.py::test_us_5_2_line_confirmations_stay_with_their_source PASSED
test_us_5_2_extraction.py::test_us_5_2_835_lines_win_over_a_scanned_copy PASSED

junit-node.xml: 3 US-5.2 cases, fail 0
  ✔ test_us_5_2_pane_unreadable_fields_highlighted (1.398166ms)
  ✔ test_us_5_2_pane_confirmed_fields_stored (2.85425ms)
  ✔ test_us_5_2_pane_receives_progress_events (0.9015ms)

$ uv run pytest -m models -k us_5_2 -rs --no-cov -p no:cacheprovider
tests/test_us_5_2_extraction.py s                                        [100%]
SKIPPED [1] tests/test_us_5_2_extraction.py:205: Qwen3-VL-8B weights not found at /Users/josoroma/Models/Qwen3-VL-8B-Instruct-4bit
====================== 1 skipped, 980 deselected in 1.52s ======================

$ make case-process CASE=case_63dbde3243b9a0fa
extracting     0%
extracting    48%
extracting    95%
done         100%
$ make case-show CASE=case_63dbde3243b9a0fa
 "needs_confirmation": [],
 "payer_name": {"value": "ACME HEALTH PLAN", "status": "extracted"},
 "claim_id": {"value": "CLAIM-77", "status": "extracted"},
 "lines": [{ "procedure_code": {"value": "99213", ...}, "service_date": {"value": "2026-09-01", ...},
             "billed_amount": {"value": "250", ...}, "paid_amount": {"value": "0", ...},
             "adjustments": [{"group_code": {"value": "CO"}, "carc": {"value": "197"}, "amount": {"value": "250"}}],
             "rarc_codes": [{"value": "N286", "status": "extracted"}] }],
 "sources": ["src_a15dfad1c4304f61", "src_7acde8457f6039ae"], "itemized_by": "src_a15dfad1c4304f61"

$ make case-process CASE=case_5c3cd175ef326fad          (EOB PDF only)
extracting     0%
extracting    95%
done         100%
$ make case-show CASE=case_5c3cd175ef326fad
needs_confirmation: ['claim_id']
claim_id: {'value': None, 'status': 'unreadable'}
payer_name: {'value': 'ACME HEALTH PLAN', 'status': 'extracted'}
line0: 99213 2026-09-01 250.00 [('CO', '197', '250.00')] ['N286']

$ make case-confirm CASE=case_5c3cd175ef326fad FIELD=claim_id VALUE=CLAIM-77           (exit 0)
ok: True | needs_confirmation: [] | claim_id: {'value': 'CLAIM-77', 'status': 'confirmed'}
$ make case-confirm CASE=case_5c3cd175ef326fad FIELD=payer_name VALUE="O'Brien Health"
ok: True | needs_confirmation: [] | payer_name: {'value': "O'Brien Health", 'status': 'confirmed'}
$ make case-confirm CASE=case_5c3cd175ef326fad FIELD=lines.0.service_date VALUE=not-a-date
curl: (22) The requested URL returned error: 422
{ "ok": false, "error": { "code": "invalid_request",
  "message": "The request did not match the expected parameters." } }
make: *** [case-confirm] Error 22                                                     (exit 2)
$ make case-confirm CASE=case_5c3cd175ef326fad FIELD=lines.0.adjustments.0.carc VALUE=1234
curl: (22) The requested URL returned error: 422   ... "code": "invalid_request" ...  (exit 2)
$ make case-show (line 0 after refusals)
{'value': '2026-09-01', 'status': 'extracted'} {'value': '197', 'status': 'extracted'}
$ make case-confirm CASE=case_5c3cd175ef326fad FIELD=claim_id
usage: make case-confirm CASE=<case id> FIELD=<field path> VALUE=<value>              (exit 2)
$ make case-process CASE=case_5c3cd175ef326fad          (re-run)
extracting     0%
extracting    95%
done         100%
needs_confirmation: [] | claim_id: {'value': 'CLAIM-77', 'status': 'confirmed'} | payer_name: {'value': "O'Brien Health", 'status': 'confirmed'}
$ make case-process CASE=case_0000000000000000
curl: (22) The requested URL returned error: 404
error: case_not_found                                                                 (exit 2)
$ make case-process CASE=case_f8194e3bbb5fc402          (empty case)
curl: (22) The requested URL returned error: 409
error: no_documents                                                                   (exit 2)

# worker log held only its "serving on 127.0.0.1:18215" line; plaintext search of the scratch store:
CLAIM-77: 0   eob.pdf: 0   O'Brien: 0   %PDF: 0   CLP*PCN: 0
```

Artifacts: `evidence/US-5.2/junit.xml`, `evidence/US-5.2/junit-node.xml`

## Failures

None.

## Notes

- Row 1, the real model: `test_us_5_2_extraction_fills_case` is marked `models` and SKIPPED here
  because the Qwen3-VL-8B weights are absent from `~/Models`. No model was downloaded. How well
  Qwen3-VL-8B reads the synthetic EOB is therefore UNVERIFIED. What exercised the scenario is
  `test_us_5_2_extraction_fills_case_offline`, which runs the offline pipeline with the fake
  model: real PDF rasterizing, the real prompt template, real reply parsing, and real
  `CaseExtraction` validation, with a canned model reply. It is backed by the 835 path
  (`test_us_5_2_835_extraction_fills_case`, which uses no model) and by the operator run, which
  also used the fake model.
- Row 4, the Hermes boundary: the test stands in for Hermes' `broadcast_plugin_event` with a
  recording sink, through the `get_event_sink` override. The pane's `ctx.onEvent` is the fake ctx's
  `emit`. Inside the gateway, `get_event_sink` resolves to
  `hermes_cli.plugin_events.broadcast_plugin_event`. A live delivery from the Hermes gateway to the
  desktop event stream was not observed. The Gherkin says "host.onEvent", while the pane uses
  `ctx.onEvent`. The spec delta words this as "the gateway event stream".
- Spec-delta scenarios (openspec/changes/us-5-2-structured-extraction/specs/) were also exercised:
  - "835 text is parsed without a model": `test_us_5_2_835_extraction_fills_case`.
  - "A re-run takes its lines from another source": `test_us_5_2_line_confirmations_stay_with_their_source`.
  - "The worker stops during extraction": `test_us_5_2_relay_reports_a_lost_worker`.
  - "Extraction runs past its deadline": `test_us_5_2_jobs_stop_at_their_deadline`,
    `test_us_5_2_relay_stops_at_its_deadline`.
  - "A reply with null lists and a malformed line": `test_us_5_2_null_lists_and_bad_items_keep_the_rest`.
- How the operator run was isolated: the real `create_app` was served by `serve_case_worker.py`,
  with a scratch `HERMES_HOME` and `MODELS_HOME`, an in-memory key provider (no Keychain item), and
  a fake vision model. The targets call the worker directly. Gateway relaying is covered by
  `test_us_5_2_gateway_relays_worker_codes`. The worker was stopped afterwards.
- Something I noticed but did not count as a failure: amounts keep the precision of the source
  they come from. The 835 gives `"250"`, and the EOB read by the model gives `"250.00"`.
