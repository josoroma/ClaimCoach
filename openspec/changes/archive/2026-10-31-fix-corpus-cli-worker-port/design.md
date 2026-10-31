# Design: corpus CLI worker port

## Context

`claimcoach/cli.py` serves both `hermes claimcoach corpus …` (Hermes' CLI) and `make corpus-*`
(`python -m claimcoach.cli corpus …`). Worker-backed subcommands build a `WorkerClient` from
`WorkerConfig(data_dir=app_data_dir())`, whose `port` defaults to 18200 and is validated to
18200–18219. The worker token lives in the data dir, not per port, so only the address is wrong.

## Goals / Non-Goals

Goals: the corpus commands reach a worker on a non-default port when the operator says which.

Non-Goals: making the gateway (`plugin_api.py`) follow a non-default port (it is the production
path and the worker runs on 18200 there); discovering the port automatically.

## Decisions

1. **An explicit `--port` on the worker-backed subcommands only.** A shared argparse parent adds
   it to `import`, `list`, `status`, `reindex`, `purge`, and `audit`; `backup`, `restore`, and the
   key commands work on files and the Keychain and take no port. Rejected: a `--port` on the
   `corpus` group (accepted, and meaningless, for the local commands); an environment variable
   read by the CLI (hidden coupling between the Makefile and the module).
2. **The range is checked where the port is parsed.** The option's type checks `PORT_RANGE`
   (`claimcoach.settings`, the same range `WorkerConfig` enforces), so `--port 80` or `--port abc`
   stops with argparse's usage error and exit 2 before any file is read or any request is sent;
   the host stays the literal `127.0.0.1` (`WorkerConfig.host`), so the token can only go to
   loopback (BR-1).
4. **The token goes only to the worker the launcher recorded.** Before sending, the CLI reads the
   launcher's PID file (`worker_status`, which also checks the process is a ClaimCoach worker) and
   sends the token only when that worker's `base_url` is the requested one; otherwise it answers
   `worker_unavailable` and sends nothing. The range 18200–18219 also holds the model servers, so
   a mistyped `--port` must not hand them, or a process of another user bound to the port, a
   token that opens case content. This validates the operator's explicit port; it does not pick
   one. Rejected: trusting any loopback listener (the review showed the token reaching a model
   server).
3. **The Makefile passes `WORKER_PORT`.** `CORPUS_PORT = --port $(WORKER_PORT)` is appended to
   the six worker-backed targets, matching how `WORKER_URL` serves the other worker targets.
   Rejected: reading the running worker's port from its PID file (the gateway would still use
   18200, so CLI and gateway would disagree silently).

## Risks / Trade-offs

- [An operator forgets `WORKER_PORT` on one target] → `worker_unavailable`, never another
  worker's data; the runbook names the variable.
- [Non-default ports are only half supported] → the gateway and pane stay on 18200; the runbook
  says another port is for a scratch or test worker with its own `HERMES_HOME`.
