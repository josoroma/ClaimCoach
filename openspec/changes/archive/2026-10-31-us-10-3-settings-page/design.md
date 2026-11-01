# Design: US-10.3 settings page for models, corpus, and retention

## Context

`ctx.registerSettingsPage` is optional (PC-3); `plugin.js` already feature-detects it and registers
`SettingsPage`, which shows the worker status. Hermes stores plugin settings under
`plugins.entries.claimcoach.settings` in the active profile's `config.yaml` and renders
`config_schema` (PC-5). `hermes_cli.plugins_settings.save_plugin_settings(plugin_id, plugin_dir,
values)` is the writer the Desktop Settings → Plugins form uses: it validates values against the
manifest's `config_schema` and refuses managed installs and keys. The worker reads
`retention_days` from each profile's `config.yaml` on every purge (`load_retention_days`).

## Goals / Non-Goals

Goals: one page that shows model and corpus status and saves the retention period, on hosts that
support settings pages, without breaking hosts that do not.

Non-Goals: editing other settings here (they stay in Settings → Plugins); downloading models from
this page (the pane's download confirmation flow, US-2.4, is unchanged); showing other profiles'
corpus scopes; importing a global-corpus bundle from this page. US-4.3 left that import UI to
this story; it is deferred (review finding): an import is a manager action that replaces global
reference material for every profile, and it needs its own confirmation design (BR-1, a local file
only). `make corpus-import` remains the path, and SPECS.md US-10.3 records the open question.

## Decisions

1. **Save through Hermes' own writer, in the gateway.** The route imports
   `hermes_cli.plugins_settings` at call time and saves `{"retention_days": n}`, so the page,
   Settings → Plugins, and the CLI share one writer with Hermes' locking, managed-key refusals,
   and schema check. Outside the gateway the import fails and the route answers
   `settings_unavailable`. Rejected: writing `config.yaml` from ClaimCoach (would bypass Hermes'
   lock and managed-install rules); a worker route (the worker is app-wide; the setting is the
   active profile's).
2. **Only retention is editable here.** It is the one setting PRD §7 names for this page; the
   others keep the generic form. The body is `{"retention_days": int}` with `extra="forbid"`, 1 to
   3650 (the model's bounds); anything else is `invalid_request`.
3. **The worker is not told; it reads.** The purge reads the profile's config each run, so the
   new period applies from the next run (at most six hours later, or `make corpus-purge`).
   Rejected: a push to the worker (two sources of truth).
4. **Corpus status is filtered in the gateway.** `GET /corpus/status` answers the global scope and
   the active profile's user scope only; another profile's path and counts are not this biller's
   business.
5. **Each section loads on its own.** A stopped worker leaves models and corpus in an
   "unavailable" state while retention, read in the gateway, still loads and saves.

6. **The page shows the period the purge uses.** `GET /settings` reads `retention_days` on its
   own (`stored_retention_days`), as the worker's `load_retention_days` does, not through the
   all-or-nothing `load_settings`; an invalid stored value answers `null` and the page says no
   closed case is purged until a valid period is saved (review finding).
7. **Every failed save is a fixed envelope.** Any error from Hermes' writer (a config it cannot
   parse, a disk error, an unreadable file) answers `settings_unavailable` and is logged by type
   only, because Hermes' messages quote config lines; only a `PermissionError` without an errno
   (Hermes' managed-install and managed-key refusals) answers `settings_managed`. A save waiting
   more than 30 s on Hermes' config lock answers `settings_unavailable` (review findings).
8. **The worker reads only the asked profile's scope.** `GET /corpus/status?profile=` opens only
   that user store, so the settings page never fetches another profile's Keychain key.

## Risks / Trade-offs

- [A shorter period purges more cases at the next run, irreversibly] → the page says so next to
  Save, and the value is validated (at least one day).
- [A save that times out may still complete once Hermes' lock frees] → the page says it was not
  saved; reopening the page shows the stored value.
- [Hermes renames `save_plugin_settings`] → the import is checked at call time and the route
  answers `settings_unavailable`; the gateway-Python probe test pins the call.
