# Runbook: Upgrade ClaimCoach

Rules: PC-2 (Desktop runs a copy of `desktop/plugin.js`), PC-5, ES-7. Later stories add data
migrations here as they introduce stored data.

## Preconditions

- `make check` passes on the target revision.
- The worker is stopped: `make worker-stop`.
- A backup of the data dir if the release notes mention a data migration
  ([corpus runbook](corpus-import-reindex-backup-restore.md)).

## Steps

1. Update the checkout and dependencies:

   ```bash
   git pull --ff-only
   make install
   make worker-venv
   ```

2. Re-validate and restart:

   ```bash
   make validate
   hermes gateway restart
   make worker-start
   ```

3. Refresh the desktop copy: Hermes Desktop → **Capabilities → Plugins** → **Rescan**.

## Verification

```bash
hermes plugins doctor claimcoach
make worker-health
```

- `doctor` reports no stale desktop copy; `worker-health` reports the new version.

### Data migrations

| From | Migration | Runs | Checked by |
| --- | --- | --- | --- |
| before US-6.1 | Each user store's `case_items` table is rebuilt once so its CHECK accepts every case-item kind (`diagnosis` from US-6.1); rows are copied unchanged, in one transaction | When the worker first opens the store | `test_us_6_1_case_items_check_migrates` |
| before US-6.3 | None at upgrade: an extraction stored earlier reads its new `denial_date` field as unreadable. Every extraction stored or confirmed afterwards holds `denial_date`, which an earlier version refuses to read | — | `test_us_6_3_older_extraction_loads` |
| before US-7.1 | The same `case_items` rebuild, once, so the CHECK accepts `draft` | When the worker first opens the store | `test_us_7_1_a_us_6_store_accepts_drafts` |

### Configuration changes

The worker copies `models.default.yaml` to `<hermes root>/plugin-data/claimcoach/models.yaml` once,
on its first start; later changes to the shipped file reach an existing copy only by hand, unless
the table below says the worker migrates it.

| From | Change to the copy | Why |
| --- | --- | --- |
| before US-7.1 | The worker adds `"--reasoning", "off"` to the `drafting` role's `command` on its next start when the copy still holds the old shipped line unchanged (`test_us_7_1_unedited_drafting_command_migrates`). If you edited that line, append `"--reasoning", "off"` to its list yourself, then `make worker-stop` and `make worker-start` | With the default (`auto`), Bonsai 27B's hidden reasoning spends the reply's token budget and every draft ends `drafting_failed` ([appeal-drafting](appeal-drafting.md)) |

## Rollback

```bash
make worker-stop
git checkout <previous tag or commit>
make install && make worker-venv
hermes gateway restart
make worker-start
```

Then **Rescan** in Capabilities → Plugins.

An earlier version opens a store migrated by a later one (the CHECK only grew) and ignores the
case items it does not know, such as diagnoses. It cannot read an extraction stored or confirmed
by US-6.3 or later (its model forbids the `denial_date` field), so such a case would not open:
rolling back past US-6.3 means restoring the backup taken before the upgrade
([corpus runbook](corpus-import-reindex-backup-restore.md)), which loses the work done since.
