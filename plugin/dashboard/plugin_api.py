"""ClaimCoach backend half: Hermes mounts ``router`` at ``/api/plugins/claimcoach/``.

Implements: US-1.1 (backend manifest target), US-1.3 (thin typed proxy to the worker).
Rules: PC-2, PC-4.

The gateway imports this file standalone (``hermes_dashboard_plugin_claimcoach``), with no parent
package, so it loads ``../_bootstrap.py`` by path to make the app package importable.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_bootstrap() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("claimcoach_bootstrap", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_load_bootstrap().ensure_app_package()

from claimcoach.api.routes import router  # noqa: E402

__all__ = ["router"]
