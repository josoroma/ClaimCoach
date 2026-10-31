# Runbook: Install and enable ClaimCoach

Story: US-1.1. Rules: PC-1 (both halves off by default), PC-2 (unified package, dev symlink),
PC-5 (manifest v2), BR-13 (state never in the install dir).

## Preconditions

- Hermes Agent ≥ 0.22.5: `hermes --version`.
- This repo checked out; dev tools installed with `make install` (uv, npm).
- Nothing else at `~/.hermes/plugins/claimcoach` (the link target), or only an older symlink.

## Steps

1. Validate the package:

   ```bash
   make validate
   ```

2. Link the package into Hermes (dev install):

   ```bash
   make plugin-link
   ```

3. Enable the Python half (agent tools and `plugin_api.py`) and restart the gateway:

   ```bash
   make plugin-enable
   hermes gateway restart
   ```

4. Enable the desktop half: Hermes Desktop → **Capabilities → Plugins** → **Rescan** → switch on
   **ClaimCoach**.

5. Start the worker so the pane can reach it: follow
   [worker-start-stop-health](worker-start-stop-health.md).

## Verification

```bash
hermes plugins list | grep claimcoach
hermes plugins doctor claimcoach
```

- `plugins list` shows `claimcoach` enabled with 3 tools.
- `doctor` reports no stale desktop copy.
- In Hermes Desktop, the **ClaimCoach** pane appears and the statusbar shows **Local-only**.

## Rollback

```bash
make plugin-disable
hermes gateway restart
make plugin-unlink
```

Then switch ClaimCoach off in **Capabilities → Plugins**. Case data in
`~/.hermes/plugin-data/claimcoach/` is untouched; removing it is a separate, deliberate step
([phi-purge](phi-purge.md)).
