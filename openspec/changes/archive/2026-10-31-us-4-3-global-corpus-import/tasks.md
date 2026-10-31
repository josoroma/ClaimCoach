# Tasks

## 1. Import

- [x] 1.1 Typed `RuleCard`, `CodeEntry`, `LetterTemplate`, `CorpusBundle`, `parse_bundle`; verify `test_us_4_3_bundle_*`
- [x] 1.2 `import_bundle`, `corpus_view`, worker routes; verify `test_us_4_3_rule_card_keeps_provenance`, `test_us_4_3_stale_card_flagged`, `test_us_4_3_missing_provenance_rejected`, `test_us_4_3_reimport_replaces`

## 2. CLI

- [x] 2.1 `claimcoach/cli.py` and `register_cli_command`; verify `test_us_4_3_hermes_cli_registered`, `test_us_4_3_cli_import_and_list`
- [x] 2.2 Runbook import section and Makefile `corpus-import`, `corpus-list`; verify `test_us_1_5_runbooks_have_sections`
- [x] 2.3 Record `evidence/US-4.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
