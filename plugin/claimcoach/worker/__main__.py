"""``python -m claimcoach.worker``: issue this launch's token and serve on loopback.

Implements: US-1.2 (new token per launch; bind ``127.0.0.1``). Rules: PRD §7.9 worker decision.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from claimcoach.settings import PORT_RANGE
from claimcoach.worker.app import create_app
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import issue_token

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the worker in the foreground until it receives SIGINT or SIGTERM.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m claimcoach.worker", description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="ClaimCoach plugin data dir")
    parser.add_argument("--port", type=int, default=PORT_RANGE.start, help="loopback port")
    args = parser.parse_args(argv)
    config = WorkerConfig(data_dir=args.data_dir, port=args.port)
    token = issue_token(config.token_path)
    uvicorn.run(
        create_app(token),
        host=config.host,
        port=config.port,
        access_log=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
