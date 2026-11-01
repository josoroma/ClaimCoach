# Review: US-10.1

Change: us-10-1-case-list-and-dashboard
Reviewer: independent `story-reviewer` agent (read-only, given the three EPIC-10 change names and changed files, not the implementer's reasoning), 2026-10-31; independent `story-tester` operator run on a scratch worker and gateway
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | A listed case that failed to open left the pane on the previous case, with its file input, paste box, and Refresh enabled: the next document for case B went into case A (BR-5) | `link.open` answers `{state: 'unavailable', caseId}` on failure, so the pane works on the selected case. Design decision 5; node "a case that fails to open stays selected, so the next document goes to it" |
| medium | The list sat outside the detail view's drop handlers, so a file dropped on the list could open in the webview | The `ClaimCoachPane` wrapper is the drop zone (`preventDefault` on dragover and drop) and hands files to the detail view (`link.drop`); the detail view stops its own drop from bubbling twice. Node "a file dropped anywhere on the pane joins the open case" |
| low | One click on a listed case discarded unsaved draft edits | `link.open` is refused with the `unsaved_draft` notice while the editor holds unsaved text. Node "opening another case waits for unsaved draft edits" |
| low | List dates were the UTC date | `localDay` shows this Mac's calendar day. Node "case rows show the open date on this Mac"; the suite passes under `TZ=Pacific/Honolulu`, `Asia/Tokyo`, and `UTC` |
| low | The error-state test rendered only the list | Node "the detail view also renders under a rejecting backend" |
| process | Reports and task boxes were pending at review time | The tester wrote `evidence/US-10.1/test-report.md` (pass, 3/3); tasks checked at close |

Also checked by the reviewer and found sound: `CorpusStore.case_index` reads no sealed value (SQLite `FILTER` aggregates, one outcome row per case, ISO-UTC order, the lock held, refused outside the user scope); `list_cases` answers an empty list without a user scope and is not audited; `CaseList` bounds; worker and gateway `GET /cases`; the envelope when the worker is down; the route pins; plugin registration with only `jsx`/`jsxs` and the allowed imports; `casePaneOf` and the updated pane tests; `make case-list` and the runbook.

## Re-verification

See the EPIC-10 and EPIC-11 `make verify` run recorded in the US-10.3 review (all four changes on one tree).
