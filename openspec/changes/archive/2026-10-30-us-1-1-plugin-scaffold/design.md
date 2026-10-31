# Design: US-1.1 Plugin Package Scaffold and Manifest

## Context

Verified against the local Hermes Agent v0.22.5 source on 2026-10-30:

- `hermes_cli/plugins_loader.py` imports a directory plugin's `__init__.py` as
  `hermes_plugins.<slug>` with `__path__ = [plugin_dir]`.
- `hermes_cli/web_server_dashboard.py` imports `dashboard/plugin_api.py` standalone (no parent
  package) as `hermes_dashboard_plugin_<name>` and mounts its `router` at `/api/plugins/<name>/`.
- `hermes_cli/plugins_manifest.py` accepts `config_schema` entries shaped
  `{type, default, description}` with types `str | int | float | bool | list | dict | secret`.
- `pm/plugin_declarations.py` treats `python_runtime: external` as "Hermes installs nothing".
- The gateway venv runs **Python 3.11.15** with pydantic 2.13, fastapi 0.133, httpx 0.28.

## Goals / Non-Goals

**Goals:** a package Hermes validates and loads; absolute `claimcoach.*` imports everywhere;
one source of truth for settings.

**Non-Goals:** real tool behavior (EPIC-9), the skill body (US-9.3), desktop UI content
(EPIC-10). The desktop half registers placeholders so US-1.4 can test registration.

## Decisions

1. **Bootstrap the app package by name.** Neither entry point runs with `plugin/` on `sys.path`,
   so `plugin/_bootstrap.py` loads `plugin/claimcoach/` as the top-level module `claimcoach`
   through `importlib` (no `sys.path` edit, which would also expose `dashboard`, `skills`, and
   `desktop` as top-level names). It refuses to proceed if a different `claimcoach` is already
   imported. *Alternative:* relative imports inside the app package — rejected because the worker
   (US-1.2) and tests import the same code by its absolute name, and a second copy under
   `hermes_plugins.claimcoach.claimcoach` would duplicate every model class.
2. **Python 3.11 floor for gateway-loaded code.** Ruff and mypy target 3.11 so nothing loaded into
   the gateway uses 3.12-only syntax. The worker venv still runs 3.12 (PRD ES-1).
3. **Settings drive the manifest.** `ClaimCoachSettings.config_schema()` renders the manifest
   block; a test compares it with `plugin.yaml`. *Alternative:* generate `plugin.yaml` at build
   time — rejected because Hermes reads the checked-in file directly (no build step).
4. **Placeholder tools answer with an envelope, not an exception.** A handler that raises is
   logged by Hermes with its traceback; a typed `not_implemented` envelope is PHI-free and
   predictable (BR-3, ES-8).
5. **Desktop half ships opt-in.** `defaultEnabled: false` matches PC-1.
6. **Only settings something reads.** `models_home` and `retention_days` are declared; a
   `worker_port` setting was dropped during review because nothing could honor it (the gateway
   always proxies to 18200, the first port of the range).

## Risks / Trade-offs

- [Hermes changes how it imports `plugin_api.py`] → the US-1.1 integration test drives the real
  loader from `~/.hermes/hermes-agent`, so a change shows up as a failing test.
- [Name collision on `claimcoach` inside the gateway] → `_bootstrap` raises `ImportError` with
  both paths instead of silently using the wrong module.
