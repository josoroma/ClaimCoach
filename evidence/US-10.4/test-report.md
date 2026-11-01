# Test Report: US-10.4 Global Corpus Import from the Settings Page

Change: us-10-4-corpus-import-page
Story: US-10.4
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run (re-test after the review fixes)
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 (`~/.hermes/hermes-agent`, venv Python 3.11.15, PyYAML 6.0.3 with libyaml); no live Hermes Desktop

## Acceptance Criteria Evaluated

Scenario 1 has two Then clauses, so it is split into rows 1 and 2. Row 1 failed in the first run;
see "History" under Notes. Every row below comes from the re-test.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "A bundle is previewed before it is imported: Then the page shows what the bundle holds and which global items it replaces" | PASS | `test_us_10_4_bundle_previewed`, `test_us_10_4_replaced_items_are_capped`, and `test_us_10_4_pane_bundle_previewed` pass, and so does the node test "the replaced items are named, kind by kind". Operator: after `v1.yaml` was imported, `checkBundle` on `v2.json` returned `replaces: 2, replaced: ["rule_card Synthpayer/timely_filing", "code CARC/197"]`. The page's `CorpusImportSection`, rendered from that state, read: "This bundle holds 3 item(s): 1 rule card(s), 2 code(s). 2 of them replace items already in the global corpus. Nothing is imported until you confirm." Then "Payers: Synthpayer.", then "Replaces: rule card Synthpayer/timely_filing, code CARC/197.", then **Import into the global corpus** and **Cancel**. `Testcare/submission` was not listed, and it was not replaced. After `v2.json` was imported, a second preview listed all 3 items, including `code CARC/50`. A cap check with 55 synthetic codes, previewed again after importing them: the gateway returned `replaces: 55` and 50 entries; the page said "Replaces: code RARC/N000, … code RARC/N049 and 5 more." |
| 2 | "A bundle is previewed before it is imported: And nothing is imported" | PASS | `test_us_10_4_bundle_previewed`: the stored items are the same before and after the preview. Operator: `checkBundle` on `v1.yaml` sent only `GET /corpus/status` and `POST /corpus/import/preview`. The worker's `GET /corpus/global` stayed `{"ok":true,"items":[]}`, and `make corpus-list` printed only its header. Previewing `v2.json` after the v1 import left `make corpus-list` unchanged: 4 rows with the v1 sources and dates |
| 3 | "The import runs only after confirmation: Then the bundle is imported into the global corpus and the page shows what was stored" | PASS | These pass: `test_us_10_4_import_after_confirmation`, `test_us_10_4_unconfirmed_import` (4 cases), `test_us_10_4_pane_import_after_confirmation`, "a failed import keeps the file for Try again and refreshes the corpus", and "the pane waits longer than the gateway". Operator: `importBundle` sent `POST /corpus/import?confirm=true` with `timeoutMs=960000`. The section said "Imported 1 code(s), 1 letter template(s), 2 rule card(s) into the global corpus." Global documents went from 0 to 4. `make corpus-list` showed the 4 items with source and verified-on date, and flagged `Testcare/submission` `STALE`. The `v2.json` import replaced the two listed items with new titles, sources, and dates. It added `CARC/50` and kept the other two; documents went from 4 to 5. Requests without confirmation (no flag, `confirm=false`, `confirm=1`, `confirm=TRUE`) each got 409 `import_not_confirmed`, and the corpus stayed empty. Try again: the worker was stopped after a preview, and the import failed with `worker_unavailable`. The file was kept, and the section said "The import may still be finishing on this Mac… try again only if nothing changed." with a **Try again** button. After the worker was restarted, the kept upload was sent again, which is what **Try again** sends. It answered "Imported 1 letter template(s) into the global corpus.", and `make corpus-list` showed `timely-filing-l1` |
| 4 | "An invalid bundle is refused: Then the page says which part is invalid and nothing is imported" | PASS | These pass: `test_us_10_4_invalid_bundle_refused` (6 cases), `_problem_never_echoes_file_text`, `_upload_limits`, `_bytes_parser_checks_size_and_name`, `_yaml_aliases_are_refused`, `_whole_bundle_problems_say_why` (3 cases), `_invented_number_keys_are_not_echoed`, `_parsing_does_not_block_the_gateway`, and `test_us_10_4_pane_invalid_bundle_refused`. Operator, page text through `checkBundle`, one problem per file: <br>• missing source: `items.1.rule_card.source: missing` <br>• invented key: `items.0.rule_card.…: extra_forbidden` <br>• invented number key `987654321`: `items.0.rule_card.…: invalid_key` <br>• bad payer: `items.0.rule_card.payer: string_pattern_mismatch` <br>• duplicate key: `invalid bundle at bundle: duplicate item key in bundle` <br>• YAML alias: "bundle uses YAML aliases, which ClaimCoach does not accept" <br>• broken YAML: "bundle is not valid YAML or JSON" <br>• `.csv` file: "a bundle is a .yaml, .yml, or .json file" <br>Each appeared in "This file is not a valid corpus bundle (…); nothing was imported." with no Import or Try again button. The confirmed import of each file got 422 `invalid_bundle`. The page refused a file over 5 MiB before reading it. The gateway also refused it: the preview answered `valid: false`, and the import got 422. The global corpus hash was the same before and after. `CANARY*` and `987654321` had 0 matches in page or gateway output and in the logs |

## Evidence Commands

```bash
make evidence STORY=US-10.4
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/corpus_import.test.mjs
npm exec --no -- tsc --noEmit -p tsconfig.json
# operator re-test, scratch harness in the session scratchpad (tester-10-4/), fresh scratch
# HERMES_HOME (the first run's moved to hermes-run1/), synthetic data only:
#   serve_worker.py: real create_app, tests/fakes make_service (FakeModelServer for embeddings,
#     InMemoryKeyProvider), status-only ModelManager over an empty scratch MODELS_HOME, scratch
#     worker.log, launcher-style worker.json so `make corpus-list` reaches it; 127.0.0.1:18218
#   serve_gateway.py: plugin/dashboard/plugin_api.py's router in Hermes' venv Python (hermes_cli on
#     PYTHONPATH) at /api/plugins/claimcoach on 127.0.0.1:18219, worker client -> 18218
#   bridge.mjs: plugin.js's checkBundle / importBundle / loadCorpus over fetch (ctx.rest stand-in,
#     one-file multipart part "file"), then renders plugin.js's CorpusImportSection (fake jsx)
#     and prints its text and buttons
#   bridge-retry.mjs: preview -> worker stopped -> importBundle -> worker back -> importBundle(kept)
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18218 GATEWAY_PORT=18219
make corpus-backup BACKUP_DIR=<scratch>/backups                       # runbook step 5
node --import ./plugin/desktop/tests/register-fakes.mjs <scratch>/bridge.mjs preview data/v1.yaml
curl -H "Authorization: Bearer $T" http://127.0.0.1:18218/corpus/global; make corpus-list
curl -F file=@v1.yaml $G/corpus/import{,?confirm=false,?confirm=1,?confirm=TRUE}
node ... bridge.mjs import data/v1.yaml; make corpus-list
node ... bridge.mjs preview data/v2.json; curl -F file=@v2.json $G/corpus/import/preview; make corpus-list
node ... bridge.mjs import data/v2.json; make corpus-list; node ... bridge.mjs preview data/v2.json
node ... bridge.mjs import data/many.json; node ... bridge.mjs preview data/many.json   # 55 codes
node ... bridge.mjs import data/<each invalid file>; curl -F file=@<each> "$G/corpus/import?confirm=true"
node ... bridge.mjs preview v1.yaml --size 5242881; curl -F file=@big.yaml $G/corpus/import{/preview,?confirm=true}
node ... bridge-retry.mjs data/v3.yaml <flags>; kill -TERM <worker>; restart worker; make corpus-list
grep -cE "CANARY|987654321|Synthpayer|Testcare|Precertification|appeals department|Synthetic remark" worker.log gateway.out
kill -TERM <worker> <gateway>; lsof -nP -iTCP:18200-18219 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-10.4
===================== 25 passed, 1554 deselected in 2.28s ======================
junit.xml: tests=25 failures=0 skipped=0
  ... the 18 from the first run, plus _replaced_items_are_capped, _yaml_aliases_are_refused,
  _parsing_does_not_block_the_gateway, _whole_bundle_problems_say_why[duplicate item key |
  payer spelled two ways | appeal_limit_days only on appeal_levels], _invented_number_keys_are_not_echoed
junit-node.xml: failures 0
  test_us_10_4_pane_bundle_previewed, test_us_10_4_pane_import_after_confirmation,
  test_us_10_4_pane_invalid_bundle_refused
corpus_import.test.mjs (whole file): ℹ tests 17  ℹ pass 17  ℹ fail 0
  (incl. "the replaced items are named, kind by kind", "picking the same file again is a change",
   "a failed import keeps the file for Try again and refreshes the corpus",
   "a failed preview offers no Try again", "the pane waits longer than the gateway")
tsc --noEmit: exit 0

=== preview v1.yaml (empty global corpus)
checkBundle -> {"state":"preview","summary":{"items":4,"byKind":{"rule_card":2,"code":1,"letter_template":1},
  "payers":["Synthpayer","Testcare"],"morePayers":0,"stale":1,"replaces":0,"replaced":[]}}
  section: This bundle holds 4 item(s): 2 rule card(s), 1 code(s), 1 letter template(s). None of them
    is in the global corpus yet. 1 were verified more than 180 days ago. Nothing is imported until you confirm.
  section: Payers: Synthpayer, Testcare.
  section: [button: Import into the global corpus]   section: [button: Cancel]
requests: GET /corpus/status | POST /corpus/import/preview
GET /corpus/global -> {"ok":true,"items":[]}; make corpus-list -> header only

=== unconfirmed: POST /corpus/import | ?confirm=false | ?confirm=1 | ?confirm=TRUE
  -> {"ok":false,"error":{"code":"import_not_confirmed",...}} HTTP 409 (each); GET /corpus/global -> items []

=== import v1.yaml
  section: Imported 1 code(s), 1 letter template(s), 2 rule card(s) into the global corpus.
corpus section after: {"cases":0,"documents":4,...}
requests: ... | POST /corpus/import?confirm=true timeoutMs=960000 | GET /corpus/status
code             CARC/197                         2026-07-01       X12 CARC list, 2026-07
letter_template  medical-necessity-l1             2026-10-01       Synthetic template library v3
rule_card        Synthpayer/timely_filing         2026-10-20       Synthetic provider manual 2026, section 7.2
rule_card        Testcare/submission              2026-01-15 STALE Synthetic Testcare manual 2026

=== preview v2.json (row 1)
checkBundle -> {..."replaces":2,"replaced":["rule_card Synthpayer/timely_filing","code CARC/197"]}
  section: This bundle holds 3 item(s): 1 rule card(s), 2 code(s). 2 of them replace items already in
    the global corpus. Nothing is imported until you confirm.
  section: Payers: Synthpayer.
  section: Replaces: rule card Synthpayer/timely_filing, code CARC/197.
  section: [button: Import into the global corpus]   section: [button: Cancel]
gateway: {"ok":true,"valid":true,...,"replaces":2,"replaced":["rule_card Synthpayer/timely_filing","code CARC/197"]}
make corpus-list -> unchanged (same 4 rows)

=== import v2.json
  section: Imported 2 code(s), 1 rule card(s) into the global corpus.     documents 4 -> 5
code             CARC/197                         2026-10-01       X12 CARC list, 2026-10
code             CARC/50                          2026-10-01       X12 CARC list, 2026-10
letter_template  medical-necessity-l1             2026-10-01       Synthetic template library v3
rule_card        Synthpayer/timely_filing         2026-10-25       Synthetic provider manual 2026, section 7.3
rule_card        Testcare/submission              2026-01-15 STALE Synthetic Testcare manual 2026
preview v2.json again -> section: Replaces: rule card Synthpayer/timely_filing, code CARC/197, code CARC/50.

=== 55 codes (cap)
  section: Imported 55 code(s) into the global corpus.
  section: This bundle holds 55 item(s): 55 code(s). 55 of them replace items already in the global corpus. ...
  section: Replaces: code RARC/N000, code RARC/N001, … code RARC/N049 and 5 more.
gateway: replaces 55 len(replaced) 50 last code RARC/N049

=== invalid files (page via checkBundle -> CorpusImportSection; then confirmed import)
bad_source.yaml  -> invalid bundle at items.1.rule_card.source: missing
bad_key.yaml     -> invalid bundle at items.0.rule_card.…: extra_forbidden
bad_numkey.yaml  -> invalid bundle at items.0.rule_card.…: invalid_key
bad_payer.yaml   -> invalid bundle at items.0.rule_card.payer: string_pattern_mismatch
bad_dup.yaml     -> invalid bundle at bundle: duplicate item key in bundle
bad_alias.yaml   -> bundle uses YAML aliases, which ClaimCoach does not accept
bad_yaml.yaml    -> bundle is not valid YAML or JSON
bundle.csv       -> a bundle is a .yaml, .yml, or .json file
  section (each): This file is not a valid corpus bundle (<problem>); nothing was imported.  [no buttons]
POST /corpus/import?confirm=true (each) ->
  {"ok":false,"error":{"code":"invalid_bundle","message":"The file is not a valid ClaimCoach corpus bundle; nothing was imported."}} HTTP 422
oversized (page, size 5242881) -> {"state":"invalid","problem":"bundle is larger than 5 MiB"}; requests: GET /corpus/status
big.yaml (5400007 bytes): preview {"ok":true,"valid":false,"problem":"bundle is larger than 5 MiB",...} HTTP 200; import 422 invalid_bundle
global corpus unchanged after invalid attempts (sha of GET /corpus/global identical)
CANARY matches in page/gateway output: 0; 987654321 matches: 0

=== Try again (bridge-retry.mjs, v3.yaml)
preview: preview
import with worker stopped -> {"state":"failed","code":"worker_unavailable","fileKept":true}
  section: The import may still be finishing on this Mac (a large bundle can take minutes). Check the
    Corpus section, then try again only if nothing changed.
  section: [button: Try again]
corpus section refreshed -> {"state":"unavailable"}
Try again -> {"state":"imported","imported":{"letter_template":1}}
  section: Imported 1 letter template(s) into the global corpus.
corpus section refreshed -> {"cases":0,"documents":61,...}
letter_template  timely-filing-l1                 2026-10-28       Synthetic template library v4

log matches (CANARY|987654321|Synthpayer|...): worker.log 0, gateway.out 0, harness.out 0
after SIGTERM: 18200-18219 free; no harness process left
real ~/.hermes: config.yaml mtime and sha1 unchanged; plugin-data/claimcoach file list unchanged
```

Artifacts: `evidence/US-10.4/junit.xml`, `evidence/US-10.4/junit-node.xml`

## Failures

None in the re-test. The first run's row 1 FAIL is resolved; see "History" under Notes.

## Notes

- History. In the first independent run, row 1 was a FAIL:
  - The preview said only how many global items a bundle replaces ("2 of them replace items
    already in the global corpus"). It did not say which ones, because `BundlePreview` carried
    `replaces: int` alone.
  - That FAIL sent the change back to the Implementer.
  - The review fixes added `replaced: list[str]` (`<kind> <key>`, at most 50) and the page's
    "Replaces: …" line, with "and N more" past the cap.
  - The re-test above was run against the fixed code on a fresh scratch Hermes root. The other
    rows passed in both runs.
- Spec-delta scenario "An unconfirmed import" (`openspec/changes/us-10-4-corpus-import-page/specs/corpus-import-page/spec.md`):
  PASS.
  - The tests cover an empty query, `confirm=false`, `confirm=1`, and `confirm=yes`. The operator
    run covered an empty query, `confirm=false`, `confirm=1`, and `confirm=TRUE`.
  - Each got 409 `import_not_confirmed`, and the global corpus was unchanged.
  - The page can send an import only from a preview, or from a failed import that kept its file
    (Try again).
- Review fixes observed by the operator run:
  - the replaced-items list and its cap
  - YAML aliases refused
  - the fixed "at bundle: duplicate item key in bundle" reason
  - a number key the file invented shown as `…`
  - a failed import keeping the file, with **Try again** and the "may still be finishing" text
  - `timeoutMs=960000` on the import request

  Covered by tests only:
  - parsing in a worker thread (`test_us_10_4_parsing_does_not_block_the_gateway`)
  - the input being cleared after each pick ("picking the same file again is a change")
  - the payer-spelled-two-ways and topic-field reasons
  - the page's own corpus refresh after a failed import ("a failed import keeps the file for Try
    again and refreshes the corpus")

  In the operator run, the corpus refresh after the failed import was the bridge's own
  `loadCorpus` call, not `SettingsPage`'s.
- No live Hermes Desktop. Not seen in a real host:
  - the **Global corpus import** section under Settings → **ClaimCoach**
  - the native file picker
  - the buttons being clicked
  - "Importing…"
  - the Corpus section refreshing on screen

  The node tests render `SettingsPage` and `CorpusImportSection` with a fake ctx, the fake SDK,
  and fake React. The operator run rendered the real `CorpusImportSection` with the fake jsx
  runtime and printed its text and buttons, from states produced by the real `checkBundle` and
  `importBundle` against the real gateway router and worker.

  `bridge.mjs` stood in for `ctx.rest`. It sent `upload` as one `multipart/form-data` part named
  `file` and threw `"<status>: <body>"` on a non-2xx answer. Two things about Hermes' real
  `ctx.rest` were not observed: how it encodes uploads, and whether it honours `timeoutMs`.
- Runbook (`docs/runbooks/desktop-pane-and-settings.md`, step 5 and Verification). Followed:
  `make corpus-backup` first, then preview, then import, then `make corpus-list`. The page's
  wording matched the runbook. The runbook's example problem format matched
  (`invalid bundle at items.N.rule_card.source: missing`). The import message lists kinds in
  the worker's order (code first). Rollback by restoring the backup was not exercised.
- Bundles are reference material, not PHI. File text appears in this report only as the
  synthetic `make corpus-list` rows and the replaced keys, which the story asks the page to show.
  Problem text never echoed titles, bodies, sources, invented keys, or bad payer values.
- How the operator run was isolated:
  - The harness sits in this session's scratchpad (`.../scratchpad/tester-10-4/`) and refuses
    any `HERMES_HOME` or `MODELS_HOME` outside it. The re-test used a fresh scratch Hermes root.
  - It used an `InMemoryKeyProvider` (no Keychain item) and an in-process `FakeModelServer` for
    embeddings. The worker served on 127.0.0.1:18218 and was restarted once for Try again. The
    gateway served on 18219, with `get_worker_client` overridden to reach 18218.
  - The harness wrote a launcher-style `worker.json` and was started with a trailing
    `-m claimcoach.worker` argument, so `make corpus-list` sent its token to the scratch worker.
  - All data was synthetic. No model was loaded or downloaded, and the scratch `MODELS_HOME`
    stayed empty.
  - Afterwards the real `~/.hermes/config.yaml` had the same mtime and SHA-1, and the
    `~/.hermes/plugin-data/claimcoach` listing (mtime and size) was the same. Ports 18200-18219
    were free after SIGTERM.
