"""``python -m claimcoach.models init|check``: write and inspect ``models.yaml`` offline.

Implements: US-2.1 (default file written to the data dir; validation errors name the entry),
US-2.4 (missing models listed without the worker). Rules: BR-1 (no network), BR-11.
Operated through ``make models-init`` and ``make models-check``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from claimcoach.models.registry import RegistryError, ensure_registry_file, load_registry
from claimcoach.models.registry import models_home as default_models_home
from claimcoach.paths import app_data_dir

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command.

    ``init`` writes the default ``models.yaml`` unless one exists and prints its path. ``check``
    validates it and prints one line per role: port, size tier, weights, venv, and directory.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success; ``1`` when ``models.yaml`` is invalid.
    """
    parser = argparse.ArgumentParser(prog="python -m claimcoach.models", description=__doc__)
    parser.add_argument("command", choices=("init", "check"))
    parser.add_argument("--data-dir", type=Path, default=None, help="ClaimCoach data dir")
    parser.add_argument("--models-home", type=Path, default=None, help="default: $MODELS_HOME")
    args = parser.parse_args(argv)
    data_dir: Path = args.data_dir or app_data_dir()
    if args.command == "init":
        print(ensure_registry_file(data_dir))  # noqa: T201
        return 0
    try:
        registry = load_registry(data_dir)
    except RegistryError as exc:
        print(f"error: {exc}")  # noqa: T201
        return 1
    home: Path = args.models_home or default_models_home()
    print(f"MODELS_HOME={home}")  # noqa: T201
    for role, spec in registry.roles.items():
        venv = "venv ok" if spec.venv_present(home) else f"no venv {spec.venv}"
        print(  # noqa: T201
            f"{role.value:<14} {spec.port}  {spec.tier_b:>2}B  {spec.weights(home):<7}  "
            f"{venv:<16} {spec.model_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
