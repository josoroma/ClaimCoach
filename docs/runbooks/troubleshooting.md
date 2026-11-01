# Runbook: Troubleshooting

Rules: PC-1, PC-2, PC-7, BR-11, BR-12. US-2.2 adds model-server failures; US-2.3 memory pressure.

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

7. **`model_unavailable`, or a role reports `unhealthy`.** Check, in order:

   ```bash
   make models-check                      # weights present? venv ok?
   lsof -nP -iTCP:<port> -sTCP:LISTEN     # port held by another program?
   tail -n 50 ~/.hermes/plugin-data/claimcoach/models/<port>.log
   ```

   Missing weights → [model-download-convert](model-download-convert.md). Missing venv → create it
   (`uv venv --python 3.12 ~/Models/.venvs/<venv>` and install the runtime). A port held by
   another program is never adopted; stop that program or change the role's `port` in
   `~/.hermes/plugin-data/claimcoach/models.yaml` (18201–18219) and restart the worker. A slow model
   needs a larger `startup_timeout_s`. The next request retries the start.

8. **Memory pressure (the Mac swaps, or a role stays `queued`).** The memory guard never keeps two
   ≥14B servers (explanation 14B, drafting 27B, transcription 24B) resident, and Voxtral only runs
   alone, so a request that needs another large model waits as `queued` until the current one is
   unloaded; an idle blocker is unloaded at once, a busy one when its request ends. The guard only
   counts ClaimCoach's own servers:

   ```bash
   make models-status                                         # which roles are ready/queued
   ps -axo pid,rss,command | grep -E 'mlx_lm|mlx_vlm|mtplx|mlx_audio' | grep -v grep
   memory_pressure | tail -1
   ```

   Stop other apps' model servers you do not need, unload idle ClaimCoach roles with
   `make models-unload ROLE=<role>`, or lower `idle_timeout_s` in `models.yaml`. A load queued
   longer than `queue_timeout_s` (default 900 s) fails with `model_busy`; retry when the current
   draft or transcription finishes.

## Verification

```bash
make worker-health
make models-status
hermes plugins doctor claimcoach
```

## Rollback

Follow [install-enable](install-enable.md) → Rollback to take ClaimCoach out of the loop entirely.
