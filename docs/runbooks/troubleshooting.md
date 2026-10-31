# Runbook: Troubleshooting

Rules: PC-1, PC-2, PC-7, BR-11. US-2.3 adds the memory-pressure section.

## Preconditions

- Access to the Mac and the Hermes profile in question.
- Never paste case documents, worker logs with case data, or tokens into a chat or ticket.

## Steps

1. **No `claimcoach_*` tools in the agent.** The Python half is off by default (PC-1):

   ```bash
   hermes plugins list | grep claimcoach
   make plugin-enable && hermes gateway restart
   ```

2. **Pane says "Worker not running".** Check the worker, then the backend half:

   ```bash
   make worker-status || make worker-start
   tail -n 50 ~/.hermes/plugin-data/claimcoach/worker/worker.log
   ```

3. **`make worker-start` fails: port in use.** Find the owner of 18200:

   ```bash
   lsof -nP -iTCP:18200 -sTCP:LISTEN
   ```

   If it is a stale ClaimCoach worker, `kill <pid>`; otherwise stop or move the other program. The
   backend half always talks to 18200, the first port of ClaimCoach's range (BR-11).

4. **`make worker-start` fails: interpreter not found.** Run `make worker-venv`.

5. **Desktop edits do not show.** Desktop runs a copy of `desktop/plugin.js` (PC-2):

   ```bash
   hermes plugins doctor claimcoach
   ```

   Then **Capabilities → Plugins → Rescan**.

6. **API returns `{"ok": false, "error": {"code": "unauthorized"}}`.** The worker restarted and
   the caller holds an old token. The proxy reads the token per request, so retry once; if it
   persists, `make worker-stop && make worker-start`.

## Verification

```bash
make worker-health
hermes plugins doctor claimcoach
```

## Rollback

Follow [install-enable](install-enable.md) → Rollback to take ClaimCoach out of the loop entirely.
