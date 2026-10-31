# Test Report: US-3.1 PHI Span Detector with Regex Validators

Change: us-3-1-phi-detector
Story: US-3.1
Verdict: pass
Coverage: 2/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`, also the worker interpreter); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

Scenario 1 has two rows: one for the detector pipeline with the fake OpenAI-compatible model standing in for Qwen3-8B, and one for the real Qwen3-8B run. The real-model run could not happen on this Mac (see Notes).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Detected spans carry a category: Then it returns typed PhiSpan results whose categories cover each of those seven types" (detector + regex validators, fake PHI model) | PASS | `test_us_3_1_spans_carry_category_with_fake_model[eob_001 … call_note_012]` (12 synthetic documents): every result span is a `PhiSpan`; the model's spans are `{NAME, ADDRESS}`; the union with the regex validators is exactly the seven categories; each category's placeholder is in the output. Also `test_us_3_1_regex_validators_cover_structured_categories` and `test_us_3_1_validator_matches[11 cases]`. Live: a worker on scratch dirs, with `phi_detection` served by the fake model server, ran `make redact FILE=doc.txt` on fixture `eob_001` → `counts: {"name": 2, "dob": 1, "member_id": 1, "mrn": 1, "ssn": 1, "address": 1, "phone": 1}` (all seven categories) |
| 2 | "Detected spans carry a category: Then it returns typed PhiSpan results whose categories cover each of those seven types" (real Qwen3-8B, `test_us_3_1_spans_carry_category`) | UNVERIFIED | `make test-models` → `SKIPPED [1] tests/test_us_3_1_phi_detector.py:95: Qwen3-8B or the mlx-lm venv is not under /Users/josoroma/Models` |
| 3 | "Redacted text replaces each span: Then none of the seeded PHI strings appear in the output text" | PASS | `test_us_3_1_redacted_text_replaces_spans[eob_001 … call_note_012]` (12 documents): no seeded PHI string appears in the output (case-insensitive check); claim number `4471-22` and code `CO-197` survive; `second_pass_hits == 0`. Also `test_us_3_1_propagation_redacts_every_form_of_a_name`, `test_us_3_1_second_pass_catches_what_spans_missed`, `test_us_3_1_worker_redact_route`. Live: the redacted `make redact` output contains none of the 10 seeded strings of `eob_001` (`leaked: []`) |

## Evidence Commands

```bash
make test-story STORY=US-3.1
make evidence STORY=US-3.1
make test-models

# Live operator commands on scratch dirs (real ~/.hermes and ~/Models untouched)
S=<scratchpad>/us31
export HERMES_HOME=$S/hermes MODELS_HOME=$S/Models
make doctor
make models-init
# Fake weights: $MODELS_HOME/Qwen3-8B-4bit/{config.json, model.safetensors}
# models.yaml: phi_detection and classification command =
#   /usr/bin/env PYTHONPATH=<repo> <repo>/.venv/bin/python -m tests.fakes.fake_model_server \
#     --host {host} --port {port} --model default_model --reply-file $S/reply.json
# $S/doc.txt = text of phi_set.json document eob_001; $S/reply.json = fake_phi_reply(eob_001)
make models-check
make start WORKER_PYTHON=$PWD/.venv/bin/python
make doctor
make redact FILE=$S/doc.txt
python3 -c '<check every seeded eob_001 string, case-insensitive, against the redacted output>'
make models-status
make stop
lsof -nP -iTCP:18200 -iTCP:18202 -sTCP:LISTEN
```

```text
== make test-story STORY=US-3.1
collected 413 items / 350 deselected / 63 selected
tests/test_us_3_1_phi_detector.py ...................................... [ 60%]
.........................                                                [100%]
====================== 63 passed, 350 deselected in 2.90s ======================

== make evidence STORY=US-3.1
- generated xml file: .../evidence/US-3.1/junit.xml -
====================== 129 passed, 585 deselected in 3.20s ====================== (re-recorded after review fixes)

== make test-models
tests/test_us_2_2_model_lifecycle.py .                                   [ 50%]
tests/test_us_3_1_phi_detector.py s                                      [100%]
SKIPPED [1] tests/test_us_3_1_phi_detector.py:95: Qwen3-8B or the mlx-lm venv is not under /Users/josoroma/Models
================ 1 passed, 1 skipped, 411 deselected in 15.68s =================

== make doctor (scratch, before start)
  ok       MODELS_HOME=<scratch>/Models
  missing  worker venv <scratch>/Models/.venvs/claimcoach (make worker-venv)
  missing  plugin link <scratch>/hermes/plugins/claimcoach (make plugin-link)
  stopped  worker (make start)
phi_detection  18202   8B  missing  no venv mlx-lm   Qwen3-8B-4bit
rc=0

== make models-check (after fake weights + edited models.yaml)
phi_detection  18202   8B  present  no venv mlx-lm   Qwen3-8B-4bit
classification 18202   8B  present  no venv mlx-lm   Qwen3-8B-4bit

== make start
{"pid":68529,"base_url":"http://127.0.0.1:18200","token_path":"<scratch>/hermes/plugin-data/claimcoach/worker/token",...}
{"ok":true,"status":"ok","version":"0.1.0"}

== make doctor (worker running)
  ok       worker on http://127.0.0.1:18200

== make redact FILE=$S/doc.txt   (rc=0)
EXPLANATION OF BENEFITS - Harborline Health Plan
Patient: [NAME]    DOB: [DOB]
Member ID: [MEMBER_ID]    MRN: [MRN]
Subscriber: [NAME]    SSN: [SSN]
Address: [ADDRESS]    Phone: [PHONE]
Claim 4471-22  Service date 2026-09-12  CPT 99214  Billed $180.00  Paid $0.00
CARC CO-197: Precertification/authorization/notification absent.
counts: {"name": 2, "dob": 1, "member_id": 1, "mrn": 1, "ssn": 1, "address": 1, "phone": 1}

== leak check
seeded: 10 leaked: []

== make models-status (phi roles)
phi_detection ready 18202 present
classification ready 18202 present

== make stop
stopped
after stop: no listeners on 18200 or 18202
  stopped  worker (make start)
```

Artifacts: `evidence/US-3.1/junit.xml` (63 tests, 0 failures, 0 skipped)

## Failures

None.

## Notes

- Row 2 is UNVERIFIED: `mlx-community/Qwen3-8B-4bit` and the `mlx-lm` venv are not under `~/Models` on this Mac, so `test_us_3_1_spans_carry_category` (marked `models`) skipped under `make test-models`. No model was downloaded. Real-model detection quality (whether Qwen3-8B finds names and addresses in every fixture) has not been observed. Rows 1 and 3 cover the detector prompt, reply parsing, regex validators, span merging, propagation, second pass, and the worker `/redact` route with a fake model that returns the names and addresses a correct model would. The other five categories come from the regex validators.
- The live run used scratch `HERMES_HOME` and `MODELS_HOME`. The scratch `MODELS_HOME` has no `.venvs/claimcoach`, so the worker ran on the project `.venv` (`make start WORKER_PYTHON=$PWD/.venv/bin/python`), as in the US-2.2 evidence. `doctor` reports the missing scratch worker venv and plugin link, which is expected for a scratch home, and exits 0.
- The fake model server runs as the configured `phi_detection`/`classification` command through `/usr/bin/env PYTHONPATH=<repo>`, so the worker's model manager spawned it on port 18202 on first use. `make stop` stopped it together with the worker.
- The real `~/.hermes/plugin-data/claimcoach/models.yaml` has mtime 02:51:39, which predates this run (03:15 to 03:17 local). Every operator command ran with the scratch env exported.
- `make test-models` also ran a US-2.2 `models` test, which passed. It is outside this story.

- After independent review (2026-10-31), fixes were re-verified with `make evidence STORY=US-3.1`
  (129 passed): bounded validators (`test_us_3_1_validators_resist_backtracking`, 10 000
  characters after each label in < 0.5 s; live, a 5 000-space document through `make redact`
  returned in 0.08 s), layout-tolerant location of model values
  (`test_us_3_1_model_values_match_across_layout_changes`,
  `test_us_3_1_unlocatable_values_fall_back_to_their_words`), wider validator coverage (30 more
  `test_us_3_1_validator_matches` cases: upper-case months, `MBI`, `Pat Acct`, snake_case keys,
  masked SSNs, extensions), two-letter surnames in name context, a 300 s per-document deadline,
  and an adversarial all-caps table EOB in the fixture set (`caps_eob_004/008/012`, all PASS in
  rows 1 and 3). `make redact` now reads the file on stdin and prints `error: <code>` on failure.
