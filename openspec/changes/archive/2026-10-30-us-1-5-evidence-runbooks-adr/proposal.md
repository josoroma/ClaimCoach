# Proposal: US-1.5 Evidence Template, Runbook Skeletons, and ADR-0001

## Why

Every later story records acceptance evidence, operations, and decisions (PRD ES-5, ES-6, ES-9).
They need one template, one place per runbook, and the first ADR before they start (SPECS.md
US-1.5).

## What Changes

- `evidence/TEMPLATE/test-report.md` in the OhMyOrch `validate-test-report` shape (`Change:`,
  `Story:`, `Verdict:`, `Coverage:`, `## Acceptance Criteria Evaluated`, `## Evidence Commands`,
  `## Failures`) and `evidence/README.md` explaining `PASS` vs `FAIL` vs `UNVERIFIED`.
- Runbooks in `docs/runbooks/`: `install-enable`, `worker-start-stop-health`,
  `model-download-convert`, `corpus-import-reindex-backup-restore`, `upgrade`, `troubleshooting`,
  `phi-purge`, `phi-incident`, each with Preconditions, Steps, Verification, Rollback. Stories
  that are not delivered yet are marked as skeletons that name the story that fills them.
- `docs/adr/0001-worker-sidecar.md` recording the PRD §7.9 worker decision.
- `tools/check_evidence.py`, a Python mirror of the OhMyOrch report contract used by tests and
  `make evidence-check`, plus a test that runs the real OhMyOrch validator when it is installed.

## Capabilities

### New Capabilities
- `delivery-evidence`: the evidence report contract, the required runbook set and its sections,
  and the ADR record.

### Modified Capabilities
- None.

## Impact

- Docs and a dev tool only. `phi-incident.md` stays a skeleton: SPECS.md US-1.5 lists the
  incident procedure and notification obligations as an open question for the Product Manager.
