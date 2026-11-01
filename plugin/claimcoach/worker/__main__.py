"""``python -m claimcoach.worker``: issue this launch's token and serve on loopback.

Implements: US-1.2 (new token per launch; bind ``127.0.0.1``), US-2.1 (``models.yaml`` written to
the data dir on first run and validated before serving), US-2.2 (model manager; orphaned model
servers of a crashed worker are reaped), US-3.4 (every log line is JSON on stderr, i.e.
worker.log), US-4.1 to US-4.5 (the corpus service over this Hermes root, user stores keyed from
the macOS Keychain), US-12.4 (the socket audit hook records every non-loopback attempt in
``worker/egress.jsonl`` from before the registry loads). Rules: PRD §7.9 worker decision, BR-11,
NFR-5.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import uvicorn

from claimcoach import PLUGIN_NAME
from claimcoach.corpus.crypto import KeychainKeyProvider
from claimcoach.corpus.embed import Embedder, Reranker, embedding_model_id
from claimcoach.corpus.service import CorpusService
from claimcoach.egress import EGRESS_AUDIT, EGRESS_LOG, file_sink
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
    config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        EGRESS_AUDIT.start("worker", file_sink(config.state_dir / EGRESS_LOG))
    except OSError:
        # GET /egress then answers audit: false, and the US-12.4 check refuses this worker.
        _log.warning("the egress audit could not open its record file; it is off")
    try:
        registry = load_registry(config.data_dir)
    except RegistryError as exc:
        _log.error("models.yaml is invalid: %s", exc)  # names the entry; scrubbed like any line
        return 2
    models = ModelManager(registry, models_home=models_home(), state_dir=config.data_dir / "models")
    models.reap_orphans()
    corpus = None
    data = config.data_dir.resolve()
    if data.name == PLUGIN_NAME and data.parent.name == "plugin-data":
        corpus = CorpusService(
            data.parents[1],  # <hermes root>/plugin-data/claimcoach -> <hermes root>
            KeychainKeyProvider(),
            Embedder(models.use),
            Reranker(models.use),
            embedding_model_id=embedding_model_id(registry),
        )
    else:
        _log.warning("the data dir is not <hermes root>/plugin-data/claimcoach; corpus disabled")
    token = issue_token(config.token_path)
    uvicorn.run(
        create_app(token, models, corpus=corpus),
        host=config.host,
        port=config.port,
        access_log=False,
        log_config=None,  # keep the JSON handler from configure_logging (US-3.4)
        server_header=False,
        loop="asyncio",  # uvloop's sockets raise no audit events (US-12.4)
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
