# Design: US-8.2 opt-in de-identified aggregation and weekly summary

## Context

US-8.1 stores one outcome per case (`overturned`, `upheld`, `written_off`, and a date) in each
profile's user store and closes the case; the retention purge later removes the case's content
and keeps the outcome (BR-7). The worker is app-wide: it opens any profile's store by name, and
the user store's sealed tables need that profile's Keychain key. Hermes renders a plugin's
`config_schema` as the Settings → Plugins form, per profile.

## Goals / Non-Goals

Goals: a weekly summary per payer and denial reason, and per payer and code, built only from
profiles that opted in, from de-identified values, without opening a case document.

Non-Goals: dollar amounts; trends across weeks; a scheduled report or notification (the
dashboard asks for a week when it opens); manager roles (Hermes has none; the dashboard is a
local route on this Mac).

## Decisions

1. **Measures (SPECS.md open question): counts and the overturn rate, no dollars.** Per payer and
   denial reason, and per payer and code: overturned, upheld, written off, the total, and
   overturned over the total (four places; none when the total is 0), plus the week's totals. A
   case counts once per code it carried. Rejected: dollar amounts (amounts recovered are not
   recorded, and billed amounts per payer and week can single out a patient's claim in a small
   practice).
2. **What is grouped by is snapshotted when the outcome is recorded, de-identified by
   construction.** `OutcomeFeatures` holds the payer as the global rule cards name it (the first
   card of the current diagnosis; the extracted payer name is case text and is never stored),
   the denial reason (an enum), and the codes (pattern-checked `CaseCode`s). Only a diagnosis of
   the case's current fields counts. It is stored as JSON in the `outcomes` row, so it survives
   the purge with the outcome; a correction after the purge keeps it. A stored snapshot longer than
   any this version writes reads as unclassified, and a row no version wrote fails only its own
   profile (`unreadable`), so one row never fails the summary. Rejected: reading the
   diagnosis at summary time (it is sealed, needs the key, and is purged after 90 days).
3. **Opt-in (SPECS.md open question): a per-profile setting, off by default.**
   `share_outcome_stats` in the manifest's `config_schema` (Settings → Plugins → ClaimCoach),
   stored in the profile's `config.yaml`. The worker reads each profile's file itself
   (`load_outcome_sharing`): only an explicit `true` shares; a missing, invalid (`"yes"`, `1`), or
   unreadable value does not, and another invalid setting cannot change it. Revoking is turning it
   off: the next summary excludes the profile, and nothing was copied out earlier, because each
   summary is built from the profiles' own tables when asked. Rejected: a central opt-in list
   (the manager could opt a biller in).
4. **The week (SPECS.md open question): ISO 8601 weeks in this Mac's time zone.** `2026-W44` runs
   from Monday 00:00 to the next Monday 00:00 local time, with the zone's daylight-saving rules
   (a week can be 167 or 169 hours), years 1970 to 9998, ASCII digits only. The default is the last
   completed week. An outcome belongs to the week its latest recording falls in. The summary names
   the zone by its IANA name when the Mac's `/etc/localtime` gives one (`America/Chicago`), else by
   its abbreviation at the week's start. Rejected: UTC weeks (a Monday-morning outcome in
   California would land in the previous week).
5. **The summary cannot read a case document.** `read_outcomes` opens `corpus.sqlite3` with
   `mode=ro`, never attaches the vector index, needs no key, and installs an SQLite authorizer
   that allows `SELECT` and reading columns of `outcomes` only: a statement that names a column
   of any other table, a function, a pragma, an attach, or a write is refused by SQLite itself.
   Rejected: opening the `CorpusStore` (it unseals with the key and can read everything).
6. **A profile that cannot be read is named, not fatal.** It is listed in `unreadable` and the
   rest are summarized; logs carry the error type only.

## Risks / Trade-offs

- [Small counts can be recognizable to someone who knows the week's cases] → the summary carries
  no amount, date, or identifier; the manager already supervises the billers whose cases these
  are, and sharing is each profile's choice.
- [Outcomes recorded before this version have no snapshot] → they count in the totals and as
  "payer without rule cards · not diagnosed".
