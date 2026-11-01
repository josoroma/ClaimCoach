# Proposal: US-10.1 Case Pane and Manager Dashboard Route

## Why

PRD §7 puts all ClaimCoach work in Hermes Desktop: a case list and case detail pane, the letter
editor, and a manager dashboard route. EPIC-5 to EPIC-8 built the detail pane (intake, fields,
diagnosis, draft editor, outcome) and the dashboard route, but the pane opens only the case it is
working on: a biller cannot find yesterday's case again, and a backend error in the pane's first
read has no error state of its own.

## What Changes

- `CorpusStore.case_index` and `CaseService.list_cases`: the profile's cases, newest first, as
  PHI-free rows (`CaseListEntry`: ID, opened/closed/purged dates, outcome, and counts of documents
  and calls, and whether it is extracted, diagnosed, or drafted). Not audited: no case content is
  read.
- Worker `GET /cases`, gateway `GET /cases` (active profile), `WorkerClient.list_cases`.
- Pane: the registered pane renders `ClaimCoachPane`, a case list view (`CaseListView`) above the
  case detail view (`CasePane`). Selecting a case opens it in the detail view (audited
  `case_opened`); a case the detail view creates appears in the list. A failed list read shows a
  fixed error state with a Retry button instead of throwing.
- JSDoc types for every new prop; plain `jsx()`/`jsxs()` (PC-3).

## Capabilities

### New Capabilities
- `desktop-case-pane`: the registered case pane with its case list and case detail views, the
  dashboard route, and their error states.

### Modified Capabilities
- None (`no-send-submit`'s pinned route tables gain `GET /cases`).

## Impact

- One read-only route; no schema change.
- Tests that render the registered pane reach the detail view through the new wrapper.
