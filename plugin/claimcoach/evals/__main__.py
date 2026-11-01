"""``python -m claimcoach.evals redaction|classification|drafts|latency|egress``: the release gates.

Implements: US-12.1 (``redaction``: exit 0 at 98% recall or above, else 1, with recall per PHI
category), US-12.2 (``classification``: exit 1 under 85% accuracy; ``drafts``: exit 1 under 70%
of drafts accepted with minor edits), US-12.3 (``latency``: exit 1 when the median upload-to-draft
time exceeds 10 minutes), US-12.4 (``egress``: exit 1 when a full case flow reaches beyond
loopback). Each writes its typed JSON report to ``<out>/US-12.x/``. Exit 2 means nothing was
measured: the worker is down, an eval set is unreadable, models are missing, a download is
running, or ``lsof`` failed. Rules: BR-11 (``--port`` inside ClaimCoach's range; the token goes only
to the worker the launcher recorded), BR-14 (the terminal shows what the report holds).
Operated through ``make eval-redaction``, ``make eval-classification``, ``make eval-drafts``,
``make eval-latency``, ``make eval-egress``, and ``make release-gate``.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, Final

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.cli import port_arg, port_client
from claimcoach.corpus.paths import active_profile
from claimcoach.egress import EGRESS_LOG
from claimcoach.evals.classification import run_classification
from claimcoach.evals.datasets import (
    DenialCase,
    DenialEvalSet,
    EvalSetError,
    load_denial_set,
    load_draft_reviews,
    load_phi_set,
)
from claimcoach.evals.draft_acceptance import score_drafts
from claimcoach.evals.egress_check import (
    EgressToolError,
    app_processes,
    preconditions,
    run_egress_check,
)
from claimcoach.evals.flow import WorkerDriver, gateway_driver
from claimcoach.evals.latency import benchmark_cases, run_latency
from claimcoach.evals.redaction_recall import run_redaction
from claimcoach.evals.report import Report, summarize, write_report
from claimcoach.evals.types import EXIT_NOT_MEASURED, exit_code
from claimcoach.paths import app_data_dir
from claimcoach.settings import PORT_RANGE
from claimcoach.worker.config import WorkerConfig

__all__ = ["REPORT_FILES", "main", "pick_egress_case"]

Out = Callable[[str], object]
REPORT_FILES: Final = {
    "redaction": "redaction-recall.json",
    "classification": "classification-accuracy.json",
    "drafts": "draft-acceptance.json",
    "latency": "latency.json",
    "egress": "egress.json",
}
"""The report each command writes under ``<out>/US-12.x/``."""


def _config(port: int) -> WorkerConfig:
    return WorkerConfig(data_dir=app_data_dir(), port=port)


def pick_egress_case(denial_set: DenialEvalSet, case_id: str | None) -> DenialCase | None:
    """The case the egress check runs: ``case_id``, else the first with a PDF (the widest flow).

    Returns:
        The case, or ``None`` when ``case_id`` is not in the set.
    """
    if case_id is not None:
        return next((c for c in denial_set.cases if c.id == case_id), None)
    with_pdf = [c for c in denial_set.cases if "eob_pdf" in c.kinds]
    return (with_pdf or denial_set.cases)[0]


class _NotMeasuredError(Exception):
    """The command cannot measure anything; the message says why (IDs and codes only)."""


class _Run:
    """One command's context: where reports go and how the worker is reached."""

    def __init__(
        self, args: argparse.Namespace, out: Out, connect: Callable[[int], WorkerClient]
    ) -> None:
        self.args = args
        self.out = out
        self.connect = connect

    def finish(self, report: Report, kept: Sequence[str] = (), profile: str = "") -> int:
        path = write_report(report, self.args.out, REPORT_FILES[self.args.command])
        for line in summarize(report):
            self.out(line)
        self.out(f"report: {path}")
        for case_id in kept:  # worker case IDs (random, no case content) and the profile name
            self.out(
                f"warning: eval case {case_id} could not be purged: make corpus-purge "
                f"PROFILE={profile or active_profile()} CASE={case_id} CONFIRM=yes"
            )
        return exit_code(report.passed)

    async def client(self) -> WorkerClient:
        client = self.connect(self.args.port)
        try:
            await client.health()
        except WorkerError as exc:
            raise _NotMeasuredError(
                f"the worker on port {self.args.port} answered {exc.code}"
            ) from exc
        return client

    async def redaction(self) -> int:
        phi_set = load_phi_set(self.args.set)
        client = await self.client()
        return self.finish(await run_redaction(client, phi_set))

    async def classification(self) -> int:
        denial_set = load_denial_set(self.args.set)
        denial_set = denial_set.model_copy(
            update={"cases": benchmark_cases(denial_set, self.args.limit)}
        )
        client = await self.client()
        driver = WorkerDriver(client, self.args.profile or active_profile())
        result, kept = await run_classification(driver, denial_set)
        return self.finish(result, kept, driver.profile)

    async def drafts(self) -> int:
        return self.finish(score_drafts(load_draft_reviews(self.args.reviews)))

    async def latency(self) -> int:
        denial_set = load_denial_set(self.args.set)
        client = await self.client()
        driver = WorkerDriver(client, self.args.profile or active_profile())
        report, kept = await run_latency(driver, denial_set, limit=self.args.limit)
        return self.finish(report, kept, driver.profile)

    async def egress(self, config_for: Callable[[int], WorkerConfig]) -> int:
        case = pick_egress_case(load_denial_set(self.args.set), self.args.case)
        if case is None:
            raise _NotMeasuredError(f"no case {self.args.case} in {self.args.set}")
        client = await self.client()
        problems = preconditions(await client.models_status())
        for problem in problems:
            self.out(f"not measured: {problem}")
        if problems:
            return EXIT_NOT_MEASURED
        config = config_for(self.args.port)
        async with gateway_driver(client) as gateway:
            report, kept = await run_egress_check(
                gateway,
                case,
                processes=app_processes(client, config),
                worker_log=config.state_dir / EGRESS_LOG,
                worker_audit=client.egress_status,
            )
        return self.finish(report, kept)


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError("must be a whole number of 1 or more")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m claimcoach.evals", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", type=Path, default=Path("evidence"), help="the evidence root")
    worker = argparse.ArgumentParser(add_help=False)
    worker.add_argument(
        "--port",
        type=port_arg,
        default=PORT_RANGE.start,
        help="the worker's port (default: %(default)s)",
    )
    cases = argparse.ArgumentParser(add_help=False)
    cases.add_argument("--set", type=Path, required=True, help="the labeled denial set (JSON)")
    profile = argparse.ArgumentParser(add_help=False)
    profile.add_argument(
        "--profile", help="the profile eval cases run in (default: the active one)"
    )
    redaction = commands.add_parser(
        "redaction", help="US-12.1 PHI recall gate", parents=[common, worker]
    )
    redaction.add_argument("--set", type=Path, required=True, help="the synthetic PHI set (JSON)")
    for name, title in (("classification", "US-12.2 accuracy"), ("latency", "US-12.3 median")):
        sub = commands.add_parser(name, help=title, parents=[common, worker, cases, profile])
        sub.add_argument("--limit", type=_positive, help="run only this many cases")
    drafts = commands.add_parser("drafts", help="US-12.2 draft acceptance", parents=[common])
    drafts.add_argument("--reviews", type=Path, required=True, help="the manager's reviews (JSON)")
    egress = commands.add_parser(
        "egress", help="US-12.4 zero-egress check", parents=[common, worker, cases]
    )
    # The router uses the gateway's active profile (HERMES_HOME), as it does inside Hermes.
    egress.add_argument("--case", help="the case ID to run (default: the first with a PDF)")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Out = print,
    connect: Callable[[int], WorkerClient] = port_client,
    config_for: Callable[[int], WorkerConfig] = _config,
) -> int:
    """Run one eval and write its report.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.
        out: Where lines go; defaults to ``print``.
        connect: Returns the worker client for a port; tests pass one for a test worker.
        config_for: Returns the worker's configuration for a port (its PID and egress files).

    Returns:
        ``0`` when the target was met, ``1`` when it was missed, ``2`` when nothing was measured.
    """
    args = _parser().parse_args(argv)
    command = _Run(args, out, connect)
    commands: dict[str, Callable[[], Coroutine[Any, Any, int]]] = {
        "redaction": command.redaction,
        "classification": command.classification,
        "drafts": command.drafts,
        "latency": command.latency,
        "egress": lambda: command.egress(config_for),
    }
    try:
        return asyncio.run(commands[args.command]())
    except (EvalSetError, _NotMeasuredError) as exc:
        out(f"not measured: {exc}")
    except EgressToolError as exc:
        out(f"not measured: {exc}")
    except WorkerError as exc:
        out(f"not measured: the worker answered {exc.code}")
    except Exception as exc:  # noqa: BLE001 - its text may hold case content: the type name only
        out(f"not measured: unexpected {type(exc).__name__}")
    return EXIT_NOT_MEASURED


if __name__ == "__main__":
    raise SystemExit(main())
