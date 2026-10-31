# Test Report: US-5.1 Create a Case and Add Documents

Change: us-5-1-case-intake
Story: US-5.1
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "A PDF or image is attached to a new case: Then the case lists the file as an attached source document" | PASS | `test_us_5_1_pdf_or_image_attached[pdf\|png\|jpeg]`: a new case (`case_` ID) starts with no documents. The upload is a Hermes `multipartBody`, and afterwards `GET /cases/{id}` lists exactly one document with matching `kind`, `filename`, `content_type`, and `size_bytes`. The decrypted stored bytes equal the upload, and neither the bytes nor the filename appear in the raw database or in the logs. The audit log holds `case_created`, `case_opened`, and `document_added`. `test_us_5_1_documents_accumulate_in_one_case`. Pane (node): `test_us_5_1_pane_drop_attaches_pdf_or_image_to_new_case` and `test_us_5_1_pane_drop_adds_to_the_open_case`. Operator: `make case-new` printed `case_63dbde3243b9a0fa` with `"documents": []`. `make case-add ... FILE=eob.pdf` returned `"kind": "pdf", "filename": "eob.pdf", "size_bytes": 2182`, and `make case-show` listed it. Refusals: `test_us_5_1_unsupported_bytes_refused[...]`, `test_us_5_1_refusals_store_nothing`, `test_us_5_1_oversized_file_part_refused_by_the_worker`, `test_us_5_1_unknown_or_closed_case_refused`. With `make case-add`, a binary file got 415 `unsupported_document` and the case still listed only `['pdf']`. An unknown case got 404 `case_not_found` |
| 2 | "Pasted 835 text is attached to a case: Then the case lists the pasted text as an attached source document" | PASS | `test_us_5_1_pasted_835_attached`: `POST /cases/{id}/paste` with the synthetic `ERA_835` returns kind `edi_835`, filename `None`, content type `text/plain; charset=utf-8`. The case lists exactly that document, and the stored bytes equal the pasted text. `test_us_5_1_pasted_letter_is_text` (non-835 text is kind `text`). `test_us_5_1_sniffs_kind_from_bytes[835\|835-bom\|835-other-delims\|837\|short-isa\|letter]`. `test_us_5_1_oversized_paste_body_refused_while_reading`. Pane (node): `test_us_5_1_pane_pasted_835_attached`. Operator: `make case-paste ... FILE=era.835` returned `"kind": "edi_835", "filename": null, "size_bytes": 456`, and `make case-show` listed it as the case's second document |

## Evidence Commands

```bash
make evidence STORY=US-5.1
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k "us_5_1 or us_5_2" -v
node --import ./plugin/desktop/tests/register-fakes.mjs --test --test-name-pattern=us_5_1 plugin/desktop/tests/
# operator run against a scratch worker (serve_case_worker.py: real create_app, in-memory key, fake vision model)
HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models .venv/bin/python -W ignore serve_case_worker.py --port 18215 &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18215
make case-new
make case-add CASE=case_63dbde3243b9a0fa FILE=<scratch>/eob.pdf      # tests.fakes.eob.synthetic_eob_pdf()
make case-paste CASE=case_63dbde3243b9a0fa FILE=<scratch>/era.835    # ERA_835 from tests/test_us_5_1_case_intake.py
make case-show CASE=case_63dbde3243b9a0fa
make case-add CASE=case_5c3cd175ef326fad FILE=<scratch>/blob.bin     # bytes \x00\x01\x02\xff\xfe...
make case-add CASE=case_0000000000000000 FILE=<scratch>/eob.pdf
make case-process CASE='bad id'
```

```text
tests/test_us_5_1_case_intake.py ....................................... [ 73%]
..............                                                           [100%]
- generated xml file: .../evidence/US-5.1/junit.xml -
====================== 53 passed, 928 deselected in 1.77s ======================

test_us_5_1_case_intake.py::test_us_5_1_pdf_or_image_attached[pdf] PASSED
test_us_5_1_case_intake.py::test_us_5_1_pdf_or_image_attached[png] PASSED
test_us_5_1_case_intake.py::test_us_5_1_pdf_or_image_attached[jpeg] PASSED
test_us_5_1_case_intake.py::test_us_5_1_documents_accumulate_in_one_case PASSED
test_us_5_1_case_intake.py::test_us_5_1_pasted_835_attached PASSED
test_us_5_1_case_intake.py::test_us_5_1_pasted_letter_is_text PASSED
test_us_5_1_case_intake.py::test_us_5_1_refusals_store_nothing PASSED
test_us_5_1_case_intake.py::test_us_5_1_unknown_or_closed_case_refused PASSED
test_us_5_1_case_intake.py::test_us_5_1_expired_attachments_purged PASSED
test_us_5_1_case_intake.py::test_us_5_1_oversized_file_part_refused_by_the_worker PASSED
test_us_5_1_case_intake.py::test_us_5_1_streamed_oversized_body_refused PASSED

junit-node.xml: tests 7, pass 7, fail 0 (3 US-5.1 cases + 4 file-level entries)
  ✔ test_us_5_1_pane_drop_attaches_pdf_or_image_to_new_case (3.351083ms)
  ✔ test_us_5_1_pane_drop_adds_to_the_open_case (0.660167ms)
  ✔ test_us_5_1_pane_pasted_835_attached (0.628333ms)

$ make case-new
{ "ok": true, "case_id": "case_63dbde3243b9a0fa", ..., "documents": [], "extraction": null, "needs_confirmation": [] }
$ make case-add CASE=case_63dbde3243b9a0fa FILE=<scratch>/eob.pdf
{ "ok": true, "case_id": "case_63dbde3243b9a0fa",
  "document": { "doc_id": "src_7acde8457f6039ae", "kind": "pdf", "filename": "eob.pdf",
                "content_type": "application/pdf", "size_bytes": 2182, ... } }
$ make case-paste CASE=case_63dbde3243b9a0fa FILE=<scratch>/era.835
{ "ok": true, "case_id": "case_63dbde3243b9a0fa",
  "document": { "doc_id": "src_a15dfad1c4304f61", "kind": "edi_835", "filename": null,
                "content_type": "text/plain; charset=utf-8", "size_bytes": 456, ... } }
$ make case-show CASE=case_63dbde3243b9a0fa
  "documents": [ { "doc_id": "src_7acde8457f6039ae", "kind": "pdf", "filename": "eob.pdf", ... },
                 { "doc_id": "src_a15dfad1c4304f61", "kind": "edi_835", "filename": null, ... } ]
$ make case-add CASE=case_5c3cd175ef326fad FILE=<scratch>/blob.bin
curl: (22) The requested URL returned error: 415
{ "ok": false, "error": { "code": "unsupported_document",
  "message": "ClaimCoach accepts PDF, PNG, JPEG, and plain-text documents only." } }
make: *** [case-add] Error 22                                  (exit 2; case still lists ['pdf'])
$ make case-add CASE=case_0000000000000000 FILE=<scratch>/eob.pdf
curl: (22) The requested URL returned error: 404
{ "ok": false, "error": { "code": "case_not_found", "message": "No such case in this profile." } }
$ make case-process CASE='bad id'
usage: make case-process CASE=<case id>                        (exit 2)

# plaintext search of every file under <scratch>/hermes/plugin-data/claimcoach/user/
CLAIM-77: 0   eob.pdf: 0   %PDF: 0   CLP*PCN: 0
```

Artifacts: `evidence/US-5.1/junit.xml`, `evidence/US-5.1/junit-node.xml`

## Failures

None.

## Notes

- Spec-delta scenarios (openspec/changes/us-5-1-case-intake/specs/) were also exercised:
  - "The pane uploads a dropped file into the open case": `test_us_5_1_pane_drop_adds_to_the_open_case`.
  - "An unsupported file is refused": `test_us_5_1_unsupported_bytes_refused[...]`,
    `test_us_5_1_refusals_store_nothing`, and `make case-add` with a binary file.
  - "A file that is too large is refused": `test_us_5_1_oversized_file_part_refused_by_the_worker`,
    `test_us_5_1_streamed_oversized_body_refused`.
  - "Expired attached files are purged" (retention-purge delta): `test_us_5_1_expired_attachments_purged`.
- How the pane was tested: the node tests drive `plugin.js` against the fake `ctx`
  (`fake_ctx.mjs`). The real Hermes desktop drop zone was not exercised by hand.
- How the operator run was isolated: the worker was the real `create_app` served by
  `serve_case_worker.py`, with a scratch `HERMES_HOME` and `MODELS_HOME`. It used an in-memory key
  provider, so no Keychain item was created, and nothing under `~/.hermes` or `~/Models` was used.
  The Makefile targets call the worker directly, not through the Hermes gateway. The gateway relay
  of intake error codes is covered by `test_us_5_1_gateway_relays_intake_codes[...]`. The worker
  was stopped after the run.
- Open question still unresolved in SPECS.md: the image formats and maximum file size. The
  implementation accepts PDF, PNG, JPEG, and UTF-8 text, with limits of 16 MiB per file and 4 MiB
  per paste. These limits come from the spec delta.
