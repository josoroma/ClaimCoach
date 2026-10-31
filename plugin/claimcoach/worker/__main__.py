"""``python -m claimcoach.worker``: issue this launch's token and serve on loopback.

Implements: US-1.2 (new token per launch; bind ``127.0.0.1``), US-2.1 (``models.yaml`` written to
the data dir on first run and validated before serving), US-2.2 (model manager; orphaned model
servers of a crashed worker are reaped), US-3.4 (every log line is JSON on stderr, i.e. worker.log).
Rules: PRD §7.9 worker decision, BR-11.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import uvicorn

from claimcoach.logs import configure_logging, get_logger
from claimcoach.models.manager import ModelManager
from claimcoach.models.registry import RegistryError, load_registry, models_home
from claimcoach.settings import PORT_RANGE
from claimcoach.worker.app import create_app
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import issue_token

__all__ = ["GRACEFUL_SHUTDOWN", "main"]

_log = get_logger("claimcoach.worker")

GRACEFUL_SHUTDOWN: Final = 5
"""Seconds uvicorn waits for in-flight requests (a model load can take minutes) before cancelling
them and running the lifespan shutdown that stops every model server."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the worker in the foreground until it receives SIGINT or SIGTERM.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: ``0`` after a clean stop, ``2`` when ``models.yaml`` is invalid.
    """
    parser = argparse.ArgumentParser(prog="python -m claimcoach.worker", description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="ClaimCoach plugin data dir")
    parser.add_argument("--port", type=int, default=PORT_RANGE.start, help="loopback port")
    args = parser.parse_args(argv)
    config = WorkerConfig(data_dir=args.data_dir, port=args.port)
    configure_logging("worker")
    try:
        registry = load_registry(config.data_dir)
    except RegistryError as exc:
        _log.error("models.yaml is invalid: %s", exc)  # names the entry; scrubbed like any line
        return 2
    models = ModelManager(registry, models_home=models_home(), state_dir=config.data_dir / "models")
    models.reap_orphans()
    token = issue_token(config.token_path)
    uvicorn.run(
        create_app(token, models),
        host=config.host,
        port=config.port,
        access_log=False,
        log_config=None,  # keep the JSON handler from configure_logging (US-3.4)
        server_header=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
