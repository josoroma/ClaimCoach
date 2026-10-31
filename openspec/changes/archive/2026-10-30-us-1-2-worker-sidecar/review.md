# Review: US-1.2

Change: us-1-2-worker-sidecar
Reviewer: independent general-purpose agent (read-only, not shown the implementer's reasoning), 2026-10-30
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | Launcher readiness probe honored `HTTP_PROXY`/`ALL_PROXY`, sending the token to a proxy | `trust_env=False`; `make worker-health` uses `--noproxy '*'` |
| medium-high | Stale `worker.json` with a reused PID was adopted as running and could be signalled | PID trusted only if `ps` shows `-m claimcoach.worker`; `test_us_1_2_status_never_adopts_an_unrelated_process` |
| medium | Unhandled exception text reached `worker.log` via Starlette's error middleware; log not 0600 | Caught at outermost middleware, log type/method/path only; log created 0600 |
| medium | Gateway (profile home) and Makefile (`HERMES_HOME`) could resolve different token files | Worker state moved to the profile-independent root (`app_data_dir`) |
| low-medium | `TimeoutExpired` escaping failed start; token left for a dead worker; unbounded wait after SIGKILL | Kill after grace, token removed, bounded waits; regression tests |
| low | 404/405/422 not enveloped (422 echoes input); unreadable token file raised | Envelope handlers; `read_token` returns `None` on any read error |
| low | Previous-launch token test used a literal; token on curl command line | Test uses a real earlier token; header passed via fd |

## Re-verification

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 133 pytest +
12 node tests at 100% coverage, evidence-check incl. OhMyOrch, 2 gate self-tests).
