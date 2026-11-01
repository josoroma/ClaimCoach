# Runbook: the ClaimCoach pane, dashboard, statusbar, and settings page

Covers EPIC-10: the right-hand **ClaimCoach** pane (US-10.1: a case list above the case detail
view), the manager dashboard route `/claimcoach/dashboard` with its sidebar entry, the
**Local-only** statusbar item (US-10.2), and the **ClaimCoach** settings page with model status,
corpus status, the retention period (US-10.3), and the global corpus import (US-10.4). The pane and the page reach the backend only
through `ctx.rest` → `plugin_api.py` → the worker on `127.0.0.1` (BR-2).

The case list holds IDs, dates, outcomes, counts, and steps only; opening a case from it is
audited `case_opened` like any other open. The settings page changes one setting, the retention
period, through Hermes' own plugin-settings writer; everything else stays in Settings → Plugins.

## Preconditions

- ClaimCoach is installed and enabled (see [install-enable](install-enable.md)) and the gateway
  was restarted after the update (`make gateway-restart`).
- The worker is running for the pane's case list and the page's model and corpus sections:
  `make start` (see [worker-start-stop-health](worker-start-stop-health.md)). The retention
  section works without it.
- For the settings page: a Hermes Desktop that provides plugin settings pages. Older hosts load
  ClaimCoach without it; the values stay editable in Settings → Plugins.

## Steps

1. Open the **ClaimCoach** pane. The **Cases** list shows the profile's newest 200 cases; the
   same rows from a terminal:

   ```bash
   make case-list
   ```

2. Select a case to open it in the detail view below the list, or drop a document anywhere on
   the pane to add it to the open case (or start one); a new case appears in the list. Save draft
   edits first: the pane does not switch cases while the editor holds unsaved text.
3. Managers open **ClaimCoach** in the sidebar for the weekly summary and the fine-tune export
   (see [outcomes-and-export](outcomes-and-export.md)).
4. Open Settings → **ClaimCoach**. Check **Models** and **Corpus**, then type a new retention
   period (1 to 3650 days) and press **Save**.
5. To import a corpus bundle (a `.yaml`, `.yml`, or `.json` file of at most 5 MiB on this Mac; the
   format is in [corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)),
   back up first with `make corpus-backup`, then under **Global corpus import** pick the file.
   The page says how many items of each kind it holds, which payers it names, how many are stale,
   and which items it replaces (for example `rule card Aetna/appeal_levels`); nothing is written
   yet. Press **Import into the global corpus**, or **Cancel**. If the import fails, **Try again**
   sends the same file; if it says the import may still be finishing, check the **Corpus** section
   (or `make corpus-list`) before trying again.

## Verification

- The pane shows **Cases** above the case detail view; with the worker stopped, the list shows
  "Cases could not be loaded…" with **Retry** instead of an error, and the status line says the
  worker is not running.
- The statusbar shows **Local-only** (or **Local-only · richer agent access on** when that setting
  is on); its tooltip says ClaimCoach runs on local models only.
- After **Save**, the page says "Saved. The next purge removes the content of cases closed more
  than N days ago." and the profile's `config.yaml` holds it:

  ```bash
  grep -n "retention_days" "$HERMES_HOME/config.yaml"
  ```

  The worker's next scheduled purge (within six hours) uses it, or run it now with
  `make corpus-purge` (see [phi-purge](phi-purge.md)).
- After an import the page says "Imported N rule card(s), …" and the **Corpus** section's count
  rises by the number of new keys (an item that replaces one with the same key leaves it as it
  was); `make corpus-list` lists the items with their source and verified-on date. A file that
  is not a valid bundle names its first problem (for example
  `invalid bundle at items.2.rule_card.source: missing`), and nothing is imported.
- A managed install answers "An administrator manages this setting; nothing was saved." Any
  other failure (a `config.yaml` Hermes cannot parse, a full disk) answers "Settings are saved
  only inside Hermes; nothing was saved."; fix the YAML in the profile's `config.yaml` and save
  again.
- "The stored retention period is invalid, so no closed case is purged" means `retention_days`
  in `config.yaml` is outside 1-3650 or not a number; save a valid period.

## Rollback

- An import cannot be undone item by item: restore the global scope from the backup taken in
  step 5 (see [corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)), or
  import a corrected bundle, which replaces items with the same keys.
- Set the retention period back on the page, or in Settings → Plugins → ClaimCoach. A purge that
  already ran cannot be undone; restore from a backup if needed (see
  [corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)).
- To hide the pane and the page, disable the plugin in Capabilities → Plugins (see
  [install-enable](install-enable.md)); cases and settings stay on disk.
