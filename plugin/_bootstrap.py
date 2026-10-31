"""Make the bundled ``claimcoach`` app package importable by its top-level name.

Implements: US-1.1 (both Hermes entry points share one app package). Rules: PC-2.

Hermes imports ``__init__.py`` as ``hermes_plugins.claimcoach`` and ``dashboard/plugin_api.py`` as a
standalone module; neither runs with ``plugin/`` on ``sys.path``. Loading the package through
``importlib`` (instead of editing ``sys.path``) keeps ``dashboard``, ``skills`` and ``desktop`` from
becoming importable top-level names inside the gateway.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

__all__ = ["APP_PACKAGE", "ensure_app_package"]

APP_PACKAGE = "claimcoach"


def ensure_app_package(package_dir: Path | None = None) -> None:
    """Import ``plugin/claimcoach`` as ``claimcoach`` unless it already is.

    Args:
        package_dir: App package directory; defaults to the one next to this file.

    Raises:
        ImportError: A different ``claimcoach`` module is already imported, or the package cannot
            be loaded.
    """
    package_dir = (package_dir or Path(__file__).resolve().parent / APP_PACKAGE).resolve()
    init_file = package_dir / "__init__.py"
    loaded = sys.modules.get(APP_PACKAGE)
    if loaded is not None:
        if Path(str(loaded.__file__)).resolve() != init_file:
            raise ImportError(
                f"another {APP_PACKAGE!r} is already imported from {loaded.__file__}; "
                f"refusing to mix it with {init_file}"
            )
        return
    spec = importlib.util.spec_from_file_location(
        APP_PACKAGE, init_file, submodule_search_locations=[str(package_dir)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {APP_PACKAGE!r} from {init_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[APP_PACKAGE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[APP_PACKAGE]
        raise
