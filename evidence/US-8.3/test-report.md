# Test Report: US-8.3 Manager-Approved Fine-Tune Export

Change: us-8-3-fine-tune-export
Story: US-8.3
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (2026.9.24)

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Export requires manager approval: Then no export file is written" | PASS | `test_us_8_3_export_requires_approval` (2 cases: no approval, and `approved: false`). With a shared, labeled outcome on file, `export_fine_tune` raises `export_not_approved` (403), the outcome reader is never called (it is patched to fail if read), and no `fine-tune` folder exists afterwards. Also `test_us_8_3_approval_is_strict` (11 cases: `"yes"`, `1`, blank or whitespace-only names, names with line or paragraph separators, an 81-character name, no name, extra keys), `test_us_8_3_refusals_through_the_gateway` (6 cases: 403 `export_not_approved` or 422 `invalid_request`, with no folder written, and `text/plain` bodies give 422). Pane (node): `test_us_8_3_pane_export_requires_approval`. The export button stays disabled without both a name and the tick, and clicking it while disabled sends only `/outcomes/summary` requests. Operator: on a scratch worker holding 3 shared outcomes (2 diagnosed), `make outcomes-export` with no `MANAGER`, with only `CONFIRM=yes`, with `MANAGER="Dana Lee"` only, with `CONFIRM=yes` exported in the shell only, and with `CONFIRM=no` each answered 403 `export_not_approved`. After all five, `<hermes>/plugin-data/claimcoach/fine-tune` did not exist. A later refusal, after approved exports, added no file and no approval log line (still 4 files, 3 log lines) |
| 2 | "Exported pairs contain no PHI: Then the export file contains none of the seeded PHI strings" | PASS | `test_us_8_3_exported_pairs_contain_no_phi`: two cases built from the synthetic 835 plus `PHI_DOCUMENTS[0]`, with the member ID confirmed as `claim_id` and, in one, the patient's name confirmed as `payer_name`. They were extracted and diagnosed, then outcomes were recorded. The export has 2 records, `leaked_strings` is empty for both the file and the API answer, and none of `CLAIM-77`, `PCN-0001`, `SYNTHETIC`, the dates, `250`, or the case ID appear. Also `test_us_8_3_a_record_is_what_the_classifier_read` (exactly 7 keys), `test_us_8_3_a_record_a_validator_matches_is_withheld` (an SSN-shaped payer is withheld and absent from the file and the log), and `test_us_8_3_amounts_are_reduced_to_a_payment_status` (7 cases; no schema field has "amount" in its name). Operator: two scratch cases, each holding the same 409-byte synthetic PHI letter (`tests/fixtures/phi`, document 0), with `claim_id` confirmed as the member ID `FUD895272471` and, on the second, `payer_name` confirmed as `Avery Vandermeer`. Both were diagnosed, then marked overturned and upheld. `make outcomes-export MANAGER="Dana Lee" CONFIRM=yes` wrote `fine-tune-20261031T214444Z-3d7f8de1.jsonl` (mode 0600 in a 0700 folder) with 2 records. None of the 10 seeded PHI strings occurs in it, as a whole word or as a substring in any case. The approval log, the export answers, and the two later export files also contain none of them. The file has no `$` and no "amount" key, and none of the case IDs, `CLAIM-77`, `PCN-0001`, `4471-22`, `Harborline`, or the service and denial dates. The PHI-named payer was exported as `payer: null` |

## Evidence Commands

```bash
make evidence STORY=US-8.3
make test-story STORY=US-8.3
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_8_3 -v
# operator run against a scratch worker (serve_export_worker.py in the scratchpad: real create_app,
# InMemoryKeyProvider, FakeModelServer for embedding, extraction, classification, and explanation,
# the synthetic CODE_BUNDLE and RULE_BUNDLE of tests/fakes/diagnosis.py imported at start)
printf 'plugins:\n  entries:\n    claimcoach:\n      settings:\n        share_outcome_stats: true\n' > <scratch>/hermes/config.yaml
PYTHONPATH=<repo> HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models .venv/bin/python -W ignore <scratch>/bin/serve_export_worker.py 18213 &
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18213
make case-new                                     # A=case_dfca6f90ba6feea8, B=case_6fd90c01f4d9cccf
make case-paste CASE=$c FILE=<scratch>/era.835; make case-paste CASE=$c FILE=<scratch>/phi_letter.txt; make case-process CASE=$c
make case-confirm CASE=$A FIELD=claim_id VALUE=FUD895272471
make case-confirm CASE=$B FIELD=claim_id VALUE=FUD895272471; make case-confirm CASE=$B FIELD=payer_name VALUE="Avery Vandermeer"
make case-diagnose CASE=$A; make case-diagnose CASE=$B
make case-new; make case-paste CASE=$C FILE=<scratch>/phi_letter.txt     # C=case_6734256df2291ebb, never diagnosed
make case-outcome CASE=$A OUTCOME=overturned; make case-outcome CASE=$B OUTCOME=upheld; make case-outcome CASE=$C OUTCOME=written_off
make outcomes-export                                        # 1  no MANAGER
make outcomes-export CONFIRM=yes                            # 1b CONFIRM, no MANAGER
make outcomes-export MANAGER="Dana Lee"                     # 2  MANAGER, no CONFIRM
(export CONFIRM=yes; make outcomes-export MANAGER="Dana Lee")   # 3  CONFIRM in the environment only
make outcomes-export MANAGER="Dana Lee" CONFIRM=no          # 3b
make outcomes-export MANAGER="Dana Lee" CONFIRM=yes         # 4  approved
ls -la / stat -f '%Sp' <scratch>/hermes/plugin-data/claimcoach/fine-tune{,/*}
cat <scratch>/hermes/plugin-data/claimcoach/fine-tune/approvals.jsonl
# a second profile with no config.yaml (not shared), one diagnosed case with an outcome
make case-new PROFILE=clinic2; make case-paste/process/diagnose ... PROFILE=clinic2; make case-outcome CASE=$D PROFILE=clinic2 OUTCOME=written_off
make outcomes-export MANAGER="Lee Manager" CONFIRM=yes     # 5  approved again (run twice, see Notes)
make outcomes-export MANAGER="Dana Lee"                     # refused again: no new file, no log line
uv run python <PHI scan: seeded strings of tests/fixtures/phi document 0 against every fine-tune file and answer>
kill -TERM <worker pid>; lsof -nP -iTCP:18213 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-8.3
collected 1313 items / 1272 deselected / 41 selected
tests/test_us_8_3_fine_tune_export.py .................................. [ 82%]
.......                                                                  [100%]
- generated xml file: .../evidence/US-8.3/junit.xml -
===================== 41 passed, 1272 deselected in 2.08s ======================
junit-node.xml: tests 9, pass 9, fail 0
  US-8.3 export requires manager approval > test_us_8_3_pane_export_requires_approval
  (the other 8 entries are per-file entries with no matching test)

$ make test-story STORY=US-8.3
===================== 41 passed, 1272 deselected in 2.13s ======================
▶ US-8.3 export requires manager approval
  ✔ test_us_8_3_pane_export_requires_approval (3.045625ms)
ℹ tests 9  ℹ pass 9  ℹ fail 0

$ uv run pytest ... -k us_8_3 -v     (41 passed, 0 failed)
test_us_8_3_export_requires_approval[request_body0..1] PASSED
test_us_8_3_approval_is_strict[approval0..10] PASSED
test_us_8_3_exported_pairs_contain_no_phi PASSED
test_us_8_3_a_record_is_what_the_classifier_read PASSED
test_us_8_3_only_labeled_outcomes_of_sharing_profiles PASSED
test_us_8_3_records_of_invalid_snapshots_are_left_out PASSED
test_us_8_3_a_record_a_validator_matches_is_withheld PASSED
test_us_8_3_an_export_with_nothing_shared_is_empty PASSED
test_us_8_3_files_are_owner_only_and_approvals_logged PASSED
test_us_8_3_a_failed_write_leaves_nothing PASSED
test_us_8_3_an_export_is_never_left_unlogged PASSED
test_us_8_3_the_approval_log_is_never_followed_through_a_link PASSED
test_us_8_3_the_approval_log_must_be_a_regular_file PASSED
test_us_8_3_an_existing_log_is_made_owner_only PASSED
test_us_8_3_the_fine_tune_folder_is_never_a_link PASSED
test_us_8_3_outcomes_recorded_after_a_clock_change_are_exported PASSED
test_us_8_3_export_through_the_gateway PASSED
test_us_8_3_refusals_through_the_gateway[body0..5] PASSED
test_us_8_3_amounts_are_reduced_to_a_payment_status[7 cases] PASSED

--- operator run (scratch worker, 127.0.0.1:18213) ---
case A holds: claim_id FUD895272471 (confirmed); documents edi_835 456 bytes, text 409 bytes (= phi_letter.txt)
B payer_name: {'value': 'Avery Vandermeer', 'status': 'confirmed'} claim_id: {'value': 'FUD895272471', 'status': 'confirmed'}
A, B diagnosed: denial_reason prior_authorization, diagnosis_stale False
outcomes: A overturned, B upheld, C written_off (closed_at = recorded_at)

before: ls: .../fine-tune: No such file or directory
=== 1: no MANAGER
curl: (22) The requested URL returned error: 403
    "error": {"code": "export_not_approved",
              "message": "A fine-tune export needs the manager's explicit approval; nothing was exported."}
make: *** [outcomes-export] Error 22
ls: .../fine-tune: No such file or directory
=== 1b: CONFIRM=yes, no MANAGER          -> 403 export_not_approved; fine-tune: No such file or directory
=== 2: MANAGER, no CONFIRM                -> 403 export_not_approved; fine-tune: No such file or directory
=== 3: CONFIRM exported in env only       -> 403 export_not_approved; fine-tune: No such file or directory
=== 3b: CONFIRM=no on command line        -> 403 export_not_approved; fine-tune: No such file or directory

=== 4: MANAGER + CONFIRM=yes
    "ok": true,
    "path": "<scratch>/hermes/plugin-data/claimcoach/fine-tune/fine-tune-20261031T214444Z-3d7f8de1.jsonl",
    "filename": "fine-tune-20261031T214444Z-3d7f8de1.jsonl",
    "records": 2, "unlabeled": 1, "withheld": 0,
    "profiles": ["default"], "unreadable": [],
    "approved_by": "Dana Lee", "approved_at": "2026-10-31T21:44:44.251484Z"
exit=0
drwx------ .../fine-tune
-rw------- .../fine-tune/approvals.jsonl                             161 bytes
-rw------- .../fine-tune/fine-tune-20261031T214444Z-3d7f8de1.jsonl   709 bytes
--- approvals.jsonl
{"filename":"fine-tune-20261031T214444Z-3d7f8de1.jsonl","records":2,"profiles":["default"],"approved_by":"Dana Lee","approved_at":"2026-10-31T21:44:44.251484Z"}
--- export file
{"format": "claimcoach-fine-tune-1", "payer": "ACME Health", "facts": {"payment": "none", "adjustments": [], "remark_codes": [], "lines": [{"procedure_code": "99213", "payment": "none", "adjustments": [{"group_code": "CO", "carc": "197"}], "remark_codes": ["N286"]}]}, "codes": ["CO-197", "N286"], "denial_reason": "prior_authorization", "appeal_likelihood": "high", "outcome": "overturned"}
{"format": "claimcoach-fine-tune-1", "payer": null, "facts": {... same ...}, "codes": ["CO-197", "N286"], "denial_reason": "prior_authorization", "appeal_likelihood": "high", "outcome": "upheld"}

PHI scan
seeded PHI strings: 10 ['Avery Vandermeer', 'VANDERMEER, AVERY', 'Avery', 'Vandermeer', '07/05/1954', '9979369', 'FUD895272471', '133-94-1993', '2247 Juniper Hollow Road, Port Ellery, OR 80210', '(950) 555-0157']
export file: 709 bytes; whole-word PHI hits []; substring PHI hits []; case text hits []
approvals.jsonl: 161 bytes; whole-word PHI hits []; substring PHI hits []; case text hits []
export answer: 507 bytes; whole-word PHI hits []; substring PHI hits []; case text hits []

=== 5: second approved export (profile clinic2 now holds a diagnosed written_off outcome, no config.yaml)
    "filename": "fine-tune-20261031T214527Z-0b5249f1.jsonl",
    "records": 2, "unlabeled": 1, "withheld": 0, "profiles": ["default"], "approved_by": "Lee Manager"
clinic2 named in no fine-tune file
approvals.jsonl after 5 (and the accidental repeat):
{"filename":"fine-tune-20261031T214444Z-3d7f8de1.jsonl","records":2,"profiles":["default"],"approved_by":"Dana Lee",...}
{"filename":"fine-tune-20261031T214527Z-0b5249f1.jsonl","records":2,"profiles":["default"],"approved_by":"Lee Manager",...}
{"filename":"fine-tune-20261031T214527Z-dfaabda7.jsonl", ...}            (3 lines)
refused again (MANAGER only): exit=2; files 4 -> 4; log lines 3 -> 3
every export file: same records as the first

final scan (all files in fine-tune/, both export answers):
approvals.jsonl                             PHI substrings found: [] | '$' or amount key: False
fine-tune-20261031T214444Z-3d7f8de1.jsonl   PHI substrings found: [] | '$' or amount key: False
fine-tune-20261031T214527Z-0b5249f1.jsonl   PHI substrings found: [] | '$' or amount key: False
fine-tune-20261031T214527Z-dfaabda7.jsonl   PHI substrings found: [] | '$' or amount key: False
export1.json / export2.json                 PHI substrings found: [] | '$' or amount key: False

after SIGTERM: port 18213 free; no serve_export_worker process
```

Artifacts: `evidence/US-8.3/junit.xml`, `evidence/US-8.3/junit-node.xml`

## Failures

None.

## Notes

- `<scratch>` is
  `/private/tmp/claude-501/-Users-josoroma--claude-spares-spare-6HVSe8/0baa7100-7ed0-415c-b36d-f465bd129adb/scratchpad/tester-8-3`,
  and `<repo>` is `/Users/josoroma/sites/ycombinator/claimcoach`.
- How the operator run was isolated: `serve_export_worker.py` (in the scratchpad, not the repo)
  served the real `create_app` with a scratch `HERMES_HOME` and `MODELS_HOME` and an
  `InMemoryKeyProvider` (no Keychain item). In-process `FakeModelServer`s stood in for embedding,
  extraction, classification, and explanation. It ran on 127.0.0.1:18213 with
  `WORKER_PORT=18213` and wrote this launch's token to `<scratch>/hermes/plugin-data/claimcoach/worker/token`.
  This follows the harness of US-6.x and US-7.x. All data was synthetic: the `ERA_835` of
  `tests/test_us_5_1_case_intake.py` and `PHI_DOCUMENTS[0]` of `tests/fixtures/phi`. The worker
  was stopped with SIGTERM, and port 18213 was free afterwards. The real `~/.hermes` was not
  touched. `~/.hermes/plugin-data/claimcoach/fine-tune` does not exist. No model was downloaded.
  The `default` profile's `config.yaml` held `share_outcome_stats: true`. `clinic2` had no
  `config.yaml`.
- Runbook step 5 reads `$HOME/.hermes/plugin-data/claimcoach/fine-tune/approvals.jsonl`. Against
  the scratch worker I read `<scratch>/hermes/plugin-data/claimcoach/fine-tune/approvals.jsonl`
  instead. The runbook path is hard-coded to `$HOME/.hermes`, not `$HERMES_HOME`. An operator with
  a non-default `HERMES_HOME` has to adjust it. This is outside the criteria.
- My last command in step 5 ran one extra approved export by mistake (a second `MANAGER="Lee
  Manager" CONFIRM=yes`). That is why there are three export files and three approval log lines.
  Each approved export wrote its own file, and none replaced another. The behavior matches
  `test_us_8_3_files_are_owner_only_and_approvals_logged`.
- The spec-delta scenarios (`openspec/changes/us-8-3-fine-tune-export/specs/fine-tune-export/spec.md`)
  were exercised as follows:
  - "Export requires manager approval" ("WHEN de-identified case/outcome pairs exist and an export
    is requested without manager approval / THEN no export file is written"): PASS, the same
    evidence as row 1.
  - "Every approved export is logged" ("WHEN the manager approves an export / THEN the export's
    file name, record count, profiles, approver, and time are appended to the approval log"):
    PASS. `test_us_8_3_files_are_owner_only_and_approvals_logged` checks the exact log lines and
    mode 0600. `test_us_8_3_an_export_is_never_left_unlogged` and
    `test_us_8_3_a_failed_write_leaves_nothing` cover failed writes. In the operator run, each
    approved export appended one line `{filename, records, profiles, approved_by, approved_at}`,
    and refusals appended none. A failing log write was not forced on the operator run, so that
    part comes from the tests only.
  - "Exported pairs contain no PHI" ("WHEN the export runs with manager approval / THEN the export
    file contains none of the seeded PHI strings"): PASS, the same evidence as row 2.
  - "Only labeled outcomes of sharing profiles are exported" ("WHEN outcomes without a current
    diagnosis, outcomes recorded before facts were kept, and outcomes of a profile that does not
    share exist / THEN none of them is exported and the unlabeled ones are counted"): PASS.
    `test_us_8_3_only_labeled_outcomes_of_sharing_profiles` gives `(records, unlabeled, withheld)
    == (1, 3, 0)` and `profiles == ["default"]`. In the operator run, the never-diagnosed case C
    was left out and counted (`unlabeled: 1`). The diagnosed outcome of the non-sharing `clinic2`
    was left out and not listed in `profiles`. Outcomes "recorded before facts were kept" (pre-US-8.3
    snapshots) could not be created through the current worker, so that part comes from the
    test only.
- The dashboard: `test_us_8_3_pane_export_requires_approval` renders the dashboard page under
  `register-fakes.mjs`. The ClaimCoach dashboard's name field, approval tick, and export button
  were not seen in a live Hermes desktop, so that is UNVERIFIED in a live app. The approval rule
  is enforced by the worker regardless of the client, and the operator run exercised it directly.
- Logging: the scratch harness did not call `configure_logging`, so the worker log was empty (0
  lines). The runbook's "the export logs its counts only" was not observed in the operator run.
  It is covered by `test_us_8_3_a_record_a_validator_matches_is_withheld`, which asserts the
  withheld SSN is absent from the captured log and the count line
  `1 records (0 unlabeled, 1 withheld)` is present. `withheld` was 0 in every operator export.
- The `make` refusals exit through curl's code (`make: *** [outcomes-export] Error 22`, shell
  exit 2). This matches `case-edit` (noted in US-7.2). It is not a defect against these criteria.
