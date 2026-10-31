"""Where ClaimCoach keeps durable state.

Implements: US-1.2 (the worker token lives in the ClaimCoach plugin data dir). Rules: BR-13,
PC-6 (state goes through Hermes' plugin data dirs and never into the install dir).

Two scopes (PRD §9): ``plugin_data_dir()`` follows the active Hermes profile (one biller's cases);
``app_data_dir()`` is profile-independent. The worker is app-wide — one process on one port serves
every profile on the Mac — so its token and PID file live in ``app_data_dir()``. For the default
profile both resolve to ``~/.hermes/plugin-data/claimcoach``.
"""

from __future__ import annotations

import os
from pathlib import Path

from claimcoach import PLUGIN_NAME

__all__ = ["app_data_dir", "plugin_data_dir"]


def _env_hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def plugin_data_dir() -> Path:
    """Return (and create) the ClaimCoach data dir of the active Hermes profile.

    Inside the gateway this is Hermes' own ``plugin_data_dir``, which follows profile switches, so
    it is resolved on every call. Outside the gateway it is ``$HERMES_HOME/plugin-data/claimcoach``
    with ``HERMES_HOME`` defaulting to ``~/.hermes``.

    Returns:
        Absolute path of the data dir.
    """
    try:
        from plugins.plugin_storage import plugin_data_dir as hermes_plugin_data_dir  # noqa: PLC0415
    except ImportError:
        return _ensure(_env_hermes_home() / "plugin-data" / PLUGIN_NAME)
    return Path(hermes_plugin_data_dir(PLUGIN_NAME)).resolve()


def app_data_dir() -> Path:
    """Return (and create) the profile-independent ``<hermes root>/plugin-data/claimcoach``.

    Inside the gateway the root is Hermes' ``get_default_hermes_root()``. Outside it, the root is
    ``HERMES_HOME`` (default ``~/.hermes``), or its grandparent when ``HERMES_HOME`` points at a
    profile (``<root>/profiles/<name>``), so the Makefile and the gateway agree on one worker.

    Returns:
        Absolute path of the data dir.
    """
    try:
        from hermes_constants import get_default_hermes_root  # noqa: PLC0415
    except ImportError:
        home = _env_hermes_home()
        root = home.parent.parent if home.parent.name == "profiles" else home
    else:
        root = Path(get_default_hermes_root())
    return _ensure(root / "plugin-data" / PLUGIN_NAME)
