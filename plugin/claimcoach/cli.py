"""``hermes claimcoach corpus …``: the manager's and operator's corpus commands.

Implements: US-4.3 (``corpus import FILE`` validates a local bundle and sends it to the worker;
``corpus list`` shows provenance and the stale flag; US-6.2 and US-6.3 add a card's required
documents and appeal limit; the worker-backed commands take ``--port``, so a worker started on
another ``WORKER_PORT`` is reached, and send the worker token only to the port the launcher
recorded for the running worker), US-4.1 (``status``, ``reindex``, ``backup``,
``restore``), US-4.2 (``key-export``, ``key-import``: back up and restore a profile's Keychain
key), US-4.5 (``purge``), US-4.6 (``audit``). Rules: BR-1 (a local file only), BR-14
(the commands print IDs, counts, dates, and global reference titles; a failure prints its error
code only), PC-4 (everything but backup, restore, and the key commands goes through the worker;
their modules are imported only when they run, never when the gateway registers the command).

Registered with Hermes through ``ctx.register_cli_command("claimcoach", …)``; the same parser
runs as ``python -m claimcoach.cli`` for the Makefile.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from pydantic import BaseModel, ValidationError

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.corpus.bundle import CorpusViewResponse, ImportResult, parse_bundle
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.paths import active_profile, hermes_root
from claimcoach.corpus.types import CorpusScope, PurgeRequest, ReindexRequest
from claimcoach.paths import app_data_dir
from claimcoach.settings import PORT_RANGE
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.launcher import worker_status
from claimcoach.worker.token import read_token

if TYPE_CHECKING:
    from claimcoach.corpus.crypto import KeychainKeyProvider

__all__ = [
    "COMMAND",
    "CliRegistrar",
    "build_parser",
    "main",
    "port_arg",
    "port_client",
    "register_cli",
    "run",
]

COMMAND: Final = "claimcoach"
CLI_TIMEOUT: Final = 900.0
"""Seconds per worker call: an import embeds every item and may first start the model."""

Out = Callable[[str], object]


class CliRegistrar(Protocol):
    """The slice of Hermes' ``PluginContext`` that CLI registration uses."""

    def register_cli_command(  # noqa: D102 - mirrors Hermes' signature
        self,
        name: str,
        help: str,  # noqa: A002 - Hermes' parameter name
        setup_fn: Callable[[argparse.ArgumentParser], None],
        handler_fn: Callable[[argparse.Namespace], None] | None = None,
        description: str = "",
    ) -> object: ...


def port_client(port: int) -> WorkerClient:
    """A client for the worker on ``port``; the token is sent only to the recorded worker."""
    config = WorkerConfig(data_dir=app_data_dir(), port=port)

    def token() -> str | None:
        # The token is sent only where the launcher recorded the running worker: a mistyped
        # --port that names a model server or another process gets nothing (worker_unavailable).
        handle = worker_status(config)
        if handle is None or handle.base_url != config.base_url:
            return None
        return read_token(config.token_path)

    return WorkerClient(config.base_url, token, timeout=CLI_TIMEOUT)


def port_arg(value: str) -> int:
    """``--port``: a port in ClaimCoach's range (BR-11), checked before anything is sent."""
    try:
        port = int(value)
    except ValueError:
        port = -1
    if port not in PORT_RANGE:
        raise argparse.ArgumentTypeError(
            f"not a ClaimCoach port ({PORT_RANGE.start}-{PORT_RANGE.stop - 1})"
        )
    return port


GROUP_DEST: Final = "claimcoach_group"
COMMAND_DEST: Final = "claimcoach_command"
"""Namespaced dests: Hermes' own top-level subparser writes ``args.command``."""

_LOCAL: Final = frozenset({"backup", "restore", "key-export", "key-import"})
"""Commands that run in this process (files and the Keychain), not through the worker."""


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """Add the ``corpus`` subcommands to ``parser`` (Hermes' ``setup_fn``)."""
    groups = parser.add_subparsers(dest=GROUP_DEST, required=True)
    corpus = groups.add_parser("corpus", help="ClaimCoach corpus scopes")
    commands = corpus.add_subparsers(dest=COMMAND_DEST, required=True)
    # The commands that call the worker take its port; the local ones (files, Keychain) do not.
    worker = argparse.ArgumentParser(add_help=False)
    worker.add_argument(
        "--port",
        type=port_arg,
        default=PORT_RANGE.start,
        help=f"the worker's port (default {PORT_RANGE.start}; make passes WORKER_PORT)",
    )
    imp = commands.add_parser(
        "import", help="import a YAML or JSON bundle into the global scope", parents=[worker]
    )
    imp.add_argument("file", type=Path)
    commands.add_parser(
        "list", help="list the global corpus with source and verified-on dates", parents=[worker]
    )
    commands.add_parser("status", help="show both scopes and their index model", parents=[worker])
    reindex = commands.add_parser(
        "reindex", help="re-embed a scope under the configured model", parents=[worker]
    )
    reindex.add_argument("--scope", choices=[s.value for s in CorpusScope], required=True)
    reindex.add_argument("--profile", help="user scope's profile (default: the active one)")
    purge = commands.add_parser(
        "purge", help="run the retention purge now, or purge one case", parents=[worker]
    )
    purge.add_argument("--profile", help="only this profile (default: every profile)")
    purge.add_argument("--case", dest="case_id", help="purge this case now (needs --confirm)")
    purge.add_argument("--confirm", action="store_true", help="approve a single-case purge")
    audit = commands.add_parser(
        "audit", help="show a profile's case-access audit log", parents=[worker]
    )
    audit.add_argument("--profile", help="profile (default: the active one)")
    audit.add_argument("--case", dest="case_id", help="only this case")
    back = commands.add_parser("backup", help="copy both scopes into a new folder")
    back.add_argument("--to", dest="dest", type=Path, required=True)
    rest = commands.add_parser("restore", help="replace the scopes from a backup folder")
    rest.add_argument("--from", dest="folder", type=Path, required=True)
    rest.add_argument("--confirm", action="store_true", help="approve replacing the scopes")
    export = commands.add_parser("key-export", help="write a profile's store key to a new file")
    export.add_argument("--profile", help="profile (default: the active one)")
    export.add_argument("--to", dest="key_file", type=Path, required=True)
    load = commands.add_parser("key-import", help="put a profile's store key into the Keychain")
    load.add_argument("--profile", help="profile (default: the active one)")
    load.add_argument("--from", dest="key_file", type=Path, required=True)
    load.add_argument("--confirm", action="store_true", help="approve replacing the Keychain item")


def build_parser() -> argparse.ArgumentParser:
    """Return the standalone parser (``python -m claimcoach.cli``)."""
    parser = argparse.ArgumentParser(prog="python -m claimcoach.cli", description=__doc__)
    setup_parser(parser)
    return parser


def _json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def _view_lines(view: CorpusViewResponse) -> list[str]:
    lines = [f"{'KIND':<16} {'KEY':<32} {'VERIFIED':<10} {'':<5} SOURCE"]
    for item in view.items:
        flag = "STALE" if item.stale else ""
        details = [
            *([f"{item.required_documents} required documents"] if item.required_documents else []),
            *([f"appeal limit {item.appeal_limit_days} days"] if item.appeal_limit_days else []),
        ]
        lines.append(
            f"{item.kind:<16} {item.key:<32} {item.verified_on.isoformat():<10} {flag:<5} "
            f"{item.source}" + (f" ({', '.join(details)})" if details else "")
        )
    return lines


def _import_line(result: ImportResult) -> str:
    counts = ", ".join(f"{count} {kind}" for kind, count in result.imported.items())
    return f"imported {counts} ({result.chunks} chunks)"


async def _worker_call(args: argparse.Namespace, client: WorkerClient) -> list[str]:
    command = getattr(args, COMMAND_DEST)
    if command == "import":
        bundle = parse_bundle(args.file)  # validated here, before anything is sent
        return [_import_line(await client.import_corpus(bundle))]
    if command == "list":
        return _view_lines(await client.corpus_view())
    if command == "status":
        return [_json(await client.corpus_status())]
    if command == "reindex":
        request = ReindexRequest(scope=args.scope, profile=args.profile or active_profile())
        return [_json(await client.reindex_corpus(request))]
    if command == "purge":
        purge = PurgeRequest(profile=args.profile, case_id=args.case_id, confirm=args.confirm)
        return [_json(await client.purge_corpus(purge))]
    return [_json(await client.corpus_audit(args.profile or active_profile(), args.case_id))]


class CommandError(ValueError):
    """A local command refused; the message is fixed and names no content."""


def keychain() -> KeychainKeyProvider:
    """The Keychain the key commands use (tests point it at a throwaway keychain)."""
    from claimcoach.corpus.crypto import KeychainKeyProvider  # noqa: PLC0415 - worker-side code

    return KeychainKeyProvider()


def _key_call(command: str, args: argparse.Namespace) -> list[str]:
    from claimcoach.corpus.crypto import key_account  # noqa: PLC0415 - worker-side code

    account = key_account(args.profile or active_profile())
    if command == "key-export":
        key = keychain().export_key(account)
        # O_EXCL: never overwrite; 0600: the key file is as sensitive as the case data.
        fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(key.hex() + "\n")
        return [f"exported the {account} key to {args.key_file}"]
    if not args.confirm:
        raise CommandError("key-import replaces the Keychain item; re-run with --confirm")
    try:
        key = bytes.fromhex(args.key_file.read_text(encoding="ascii").strip())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CommandError("the key file cannot be read") from exc
    keychain().store_key(account, key, replace=True)
    return [f"imported the {account} key"]


def _local_call(command: str, args: argparse.Namespace) -> list[str]:
    # Imported here: the gateway imports this module to register the command (PC-4).
    from claimcoach.corpus.backup import backup, restore  # noqa: PLC0415

    if command.startswith("key-"):
        return _key_call(command, args)
    if command == "backup":
        return [f"backed up to {backup(hermes_root(), args.dest)}"]
    if not args.confirm:
        raise CommandError("restore replaces the corpus scopes; re-run with --confirm")
    if worker_status(WorkerConfig(data_dir=app_data_dir())) is not None:
        raise CommandError("stop the worker first (make stop)")
    return [f"restored {', '.join(restore(hermes_root(), args.folder))}"]


def run(
    args: argparse.Namespace,
    *,
    client: WorkerClient | None = None,
    out: Out = print,
    runner: Callable[[Coroutine[Any, Any, list[str]]], list[str]] = asyncio.run,
) -> int:
    """Run one parsed ``corpus`` command.

    Args:
        args: Parsed arguments.
        client: Worker client (tests pass one over an ASGI transport).
        out: Where to write lines.
        runner: Runs the worker coroutine.

    Returns:
        ``0`` on success, ``1`` when the worker refused or failed, ``2`` for bad input.
    """
    command = getattr(args, COMMAND_DEST)
    try:
        if command in _LOCAL:
            lines = _local_call(command, args)
        else:
            lines = runner(_worker_call(args, client or port_client(args.port)))
    except ValidationError:
        out("error: invalid arguments")
        return 2
    except ValueError as exc:  # BundleError, BackupError, InvalidProfileError: fixed messages
        out(f"error: {exc}")
        return 2
    except CorpusError as exc:  # the Keychain refused (key-export, key-import)
        out(f"error: {exc.code}")
        return 1
    except OSError:  # e.g. key-export onto an existing file
        out("error: the file cannot be written")
        return 2
    except WorkerError as exc:
        out(f"error: {exc.code}")
        return 1
    for line in lines:
        out(line)
    return 0


def _handle(args: argparse.Namespace) -> None:
    code = run(args)
    if code:
        raise SystemExit(code)


def register_cli(ctx: CliRegistrar) -> None:
    """Register ``hermes claimcoach`` with Hermes."""
    ctx.register_cli_command(
        COMMAND,
        "ClaimCoach corpus commands (import, list, status, reindex, purge, audit, backup, keys)",
        setup_parser,
        _handle,
        description=__doc__ or "",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``python -m claimcoach.cli``."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
