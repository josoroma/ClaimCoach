# Test Report: US-1.5 Evidence Template, Runbook Skeletons, and ADR-0001

Change: us-1-5-evidence-runbooks-adr
Story: US-1.5
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-30
Tester: Claude Code (Opus 5.5), independent run after implementation
Environment: macOS (Darwin 27.2.0, Apple Silicon); Python 3.12.9; OhMyOrch at ~/sites/OhMyOrch

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Evidence template follows the OhMyOrch report contract: Then the validator accepts a report that quotes each criterion with PASS, FAIL, or UNVERIFIED and the command and output" | PASS | `test_us_1_5_reports_pass_ohmyorch_validator` runs the real `ohmyorch validate-test-report` on a report rendered from the template (with a PASS and an UNVERIFIED row) → "RESULT: PASS"; `make evidence-check` runs it on all five delivered reports → PASS each; `test_us_1_5_evidence_template_contract` and 13 rejection cases for `tools/check_evidence.py` passed |
| 2 | "Required runbooks exist with the four sections: Then install-enable, worker-start-stop-health, model-download-convert, corpus-import-reindex-backup-restore, upgrade, troubleshooting, and phi-purge runbooks exist and each has Preconditions, Steps, Verification, and Rollback headings" | PASS | `test_us_1_5_runbooks_have_sections` → 8 runbooks (the 7 listed plus `phi-incident`) each have the 4 headings in order |
| 3 | "ADR-0001 records the worker decision: Then it records the worker decision from PRD §7.9 with status, context, decision, and consequences" | PASS | `test_us_1_5_adr_0001_present` → `docs/adr/0001-worker-sidecar.md` has `Status: Accepted`, Context, Decision, Consequences, and the §7.9 facts (venv, `127.0.0.1:18200`, `token_urlsafe`, `0600`) |

## Evidence Commands

```bash
make evidence STORY=US-1.5
make evidence-check
```

```text
tests/test_us_1_5_evidence_docs.py ...........................
27 passed

ok   US-1.1
ok   US-1.2
ok   US-1.3
ok   US-1.4
ok   US-1.5
(OhMyOrch validate-test-report --quiet on each report: exit 0)
```

Artifacts: `evidence/US-1.5/junit.xml`

## Failures

None.

## Notes

- `docs/runbooks/phi-incident.md` exists with the four sections but its procedure is marked
  **NEEDS CLARIFICATION**: SPECS.md lists the incident steps and notification obligations as an
  open question for the Product Manager.
- Runbooks for stories not delivered yet (model download, corpus, PHI purge) are skeletons that
  name the story that fills them; `docs/runbooks/README.md` tracks their state.
