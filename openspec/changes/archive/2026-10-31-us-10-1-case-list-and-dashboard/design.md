# Design: US-10.1 case list and case detail pane, dashboard route

## Context

`plugin.js` registers a right-hand pane (`CasePane`, the case detail view built by EPIC-5 to
EPIC-8 and US-11.1), the `/claimcoach/dashboard` route with its sidebar entry (US-8.2, US-8.3),
the statusbar item, and the settings page. The backend has `POST /cases` and `GET /cases/{id}`
(audited `case_opened`) but no way to list a profile's cases.

## Goals / Non-Goals

Goals: a case list and a case detail view in the pane; the dashboard route registered; every
backend error in the pane's first reads rendered as an error state.

Non-Goals: search or filters over cases; showing case content (payer, claim number, amounts) in
the list; a second route for the case list.

## Decisions

1. **The list holds no case content.** Each row is the case ID, its dates, its outcome, counts of
   documents and calls, and which steps ran (extracted, diagnosed, drafted), read from row
   metadata and item kinds without unsealing a payload. So listing is not a case access and is not
   audited; opening a case from the list is, as before. Rejected: payer and claim number in each
   row (every list read would unseal every case: audit noise, or a silent PHI read).
2. **Newest 200 cases.** `MAX_LISTED_CASES = 200`, newest first by open date; older cases are
   still opened by ID (`make case-show`). Rejected: paging (no practice has asked; adds a cursor
   to a PHI-free list for no gain).
3. **A profile without a user scope lists no cases.** A new biller sees an empty list, not
   `profile_not_found`.
4. **`ClaimCoachPane` wraps the two views; they share one link object.** The list calls
   `link.open(caseId)`, which the detail view sets on each render to open the case through its own
   action queue (the last action wins, as for every other action). The detail view calls
   `link.changed()` when it starts work on a case the list may not show yet, and the list reloads.
   Rejected: lifting the detail view's state into the wrapper (a rewrite of every EPIC-5 to EPIC-8
   handler for no behaviour change).
5. **The pane is one drop zone; switching cases is guarded.** The wrapper takes drops on the list
   and hands them to the detail view (`link.drop`), so a file dropped anywhere never opens in the
   webview; the detail view stops its own drop from reaching the wrapper twice. Opening a listed
   case is refused with a notice while the draft editor holds unsaved text, and a listed case that
   fails to open stays the pane's case, so the next document or Refresh goes to it (review
   findings). List dates are this Mac's calendar day.
6. **Error state.** The list's read becomes `{ state: 'unavailable' }` on any rejection (an
   envelope, a disabled backend half, a stopped worker) and renders a fixed message with Retry;
   envelope text is never shown (BR-14). The worker status line already does the same.

## Risks / Trade-offs

- [The list can be stale while the detail view works on another case] → it reloads when the
  detail view moves to a new case, and has a Refresh list button.
- [Counts reveal how many documents a case holds] → counts are not PHI; the list is shown only in
  the biller's own pane, for the active profile.
