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

## Rollback

```bash
make worker-stop
git checkout <previous tag or commit>
make install && make worker-venv
hermes gateway restart
make worker-start
```

Then **Rescan** in Capabilities → Plugins.
