# Review: US-4.6

Change: us-4-6-case-access-audit
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-5-retention-purge
Verdict: pass after fixes; scope still needs Product Manager sign-off (NEEDS CLARIFICATION defaults)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | `INSERT OR REPLACE` / `REPLACE INTO` rewrote entries past the UPDATE/DELETE triggers | `audit_log_no_overwrite` trigger; `test_us_4_6_audit_log_append_only[…INSERT OR REPLACE…, …REPLACE INTO…]` |
| medium | Restore replaces audit entries written after the backup | Documented in the restore runbook (record the restore outside ClaimCoach) and as a design risk; a separate audit file is a follow-up if the Product Manager wants it |
| medium | `audit` on a mistyped profile created a ghost scope and answered "no entries" | Reads never create; `profile_not_found` (see US-4.1 review) |
| low | Policy and manual purges were indistinguishable | `case_purged` (policy) vs `case_purged_on_request`; `test_us_4_6_every_case_action_audited_without_phi` |
| low | Content readers (`documents`, `chunks`, `search`) are not audited | Recorded in design: case routes (US-5.x) must call `open_case` first; retrieval runs only inside a request that opened the case |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
