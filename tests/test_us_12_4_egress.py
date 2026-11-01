"""US-12.4 Zero-Egress Check for Case Content.

Scenario: a full case flow makes no non-loopback connection. Also: what the check catches (an
attempt by the ``plugin_api`` half, a record from the worker's hook, a connection an ``lsof``
sample sees), what it ignores (loopback, Unix sockets, worker records from before the flow), its
preconditions (weights present, no download running), the processes it watches, the ``lsof``
sampler and parser, the audit hook and its record file, the worker entry point starting the hook,
the gateway driver's failures, and the CLI. The real-app check is under the ``models`` marker.
Rules: ES-4, ES-5, NFR-5, BR-1, BR-11, BR-14.
"""

from __future__ import annotations

import _socket
import asyncio
import contextlib
import os
import socket
import stat
import subprocess
import sys
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from claimcoach.api.client import WorkerClient, WorkerUnavailableError
from claimcoach.egress import (
    EGRESS_AUDIT,
    EGRESS_LOG,
    EgressAudit,
    EgressRecord,
    EgressStatus,
    file_sink,
    read_records,
)
from claimcoach.evals import __main__ as evals_main
from claimcoach.evals import egress_check
from claimcoach.evals.__main__ import main, pick_egress_case
from claimcoach.evals.datasets import DenialCase
from claimcoach.evals.egress_check import (
    EgressAuditOffError,
    EgressLogError,
    EgressToolError,
    app_processes,
    parse_lsof,
    preconditions,
    run_egress_check,
    sample_lsof,
)
from claimcoach.evals.flow import FlowError, GatewayDriver, WorkerDriver, gateway_driver
from claimcoach.evals.report import summarize, write_report
from claimcoach.evals.types import EgressFinding, EgressReport
from claimcoach.letters.types import ExportedFile
from claimcoach.models.types import ModelRole, ModelsStatusResponse, ModelStatus
from claimcoach.paths import app_data_dir
from claimcoach.worker import __main__ as worker_main
from claimcoach.worker.app import create_app
from claimcoach.worker.config import WorkerConfig, WorkerHandle
from tests.fakes.corpus import TOKEN
from tests.fakes.evals import DENIAL_SET, EvalWorker, connect_to, eval_worker, running_worker_port
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.model_env import build_model_env
from tests.fixtures.denials.generate import FIXTURE_PATH

REPORT = Path("US-12.4") / "egress.json"
PDF_CASE = pick_egress_case(DENIAL_SET, None)
NOW = datetime(2026, 10, 31, tzinfo=UTC)


@pytest.fixture
def worker(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[EvalWorker]:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    with eval_worker(tmp_path / "hermes", corpus_server) as served:
        yield served


GROUP = os.getpgid(0)
"""This test's process group: the worker app and the fake model servers all run in it."""


def this_process() -> Callable[[], Coroutine[Any, Any, dict[int, str]]]:
    async def processes() -> dict[int, str]:
        return {GROUP: "worker"}

    return processes


def audit_answers(
    *statuses: EgressStatus,
) -> Callable[[], Coroutine[Any, Any, EgressStatus]]:
    """``GET /egress`` answering ``statuses`` in turn (the last one from then on)."""
    answers = list(statuses) or [EgressStatus(audit=True, dropped=0)]

    async def answer() -> EgressStatus:
        return answers.pop(0) if len(answers) > 1 else answers[0]

    return answer


def check(
    worker: EvalWorker,
    tmp_path: Path,
    *,
    case: DenialCase | None = PDF_CASE,
    sampler: Callable[[Sequence[int]], Awaitable[str]] = sample_lsof,
    processes: Callable[[], Coroutine[Any, Any, dict[int, str]]] | None = None,
    worker_audit: Callable[[], Coroutine[Any, Any, EgressStatus]] | None = None,
) -> EgressReport:
    assert case is not None

    async def go() -> EgressReport:
        async with gateway_driver(worker.client()) as gateway:
            report, kept = await run_egress_check(
                gateway,
                case,
                processes=processes or this_process(),
                worker_log=tmp_path / EGRESS_LOG,
                worker_audit=worker_audit or audit_answers(),
                sampler=sampler,
                interval=0.01,
            )
            assert kept == []
            return report

    return asyncio.run(go())


# --- Scenario: A full case flow makes no non-loopback connection ---------------------------------


def test_us_12_4_full_flow_no_non_loopback_connection(worker: EvalWorker, tmp_path: Path) -> None:
    assert PDF_CASE is not None
    assert "eob_pdf" in PDF_CASE.kinds  # the widest flow: the vision model reads a page image
    sampled: list[str] = []

    async def real_lsof(pids: Sequence[int]) -> str:
        output = await sample_lsof(pids)
        sampled.append(output)
        return output

    report = check(worker, tmp_path, sampler=real_lsof)

    assert report.flow_completed  # upload, extraction, diagnosis, draft, and export
    assert report.error_code is None
    assert report.findings == []
    assert report.passed
    assert report.samples >= 2
    assert f"worker:{GROUP}" in report.processes
    assert f"plugin_api:{os.getpid()}" in report.processes
    assert report.observers == {
        f"plugin_api:{os.getpid()}": ["audit"],
        f"worker:{GROUP}": ["audit", "lsof"],
    }
    # lsof really sampled this process (the fake model servers listen in it), and every
    # connection it saw was to loopback.
    assert any(f"p{os.getpid()}" in output.splitlines() for output in sampled)
    remotes = {host for output in sampled for _g, _pid, host, _port in parse_lsof(output)}
    assert remotes <= {"127.0.0.1", "::1"}


# --- What the check catches ----------------------------------------------------------------------


def test_us_12_4_plugin_api_attempt_is_caught(worker: EvalWorker, tmp_path: Path) -> None:
    async def attempt(_pids: Sequence[int]) -> str:
        # A real connect, past the test socket guard (a UDP connect sends nothing).
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, contextlib.suppress(OSError):
            _socket.socket.connect(sock, ("203.0.113.7", 443))
        sys.audit("socket.getaddrinfo", "payer.example", 443, 0, 0, 0)
        return ""

    report = check(worker, tmp_path, sampler=attempt)

    assert report.flow_completed
    assert not report.passed
    pairs = {(f.source, f.process, f.event, f.host, f.port) for f in report.findings}
    assert ("audit", "plugin_api", "connect", "203.0.113.7", 443) in pairs
    assert ("audit", "plugin_api", "resolve", "payer.example", 443) in pairs


def test_us_12_4_worker_records_during_the_flow_are_caught(
    worker: EvalWorker, tmp_path: Path
) -> None:
    log = tmp_path / EGRESS_LOG
    old = EgressRecord(at=NOW, process="worker", pid=1, event="connect", host="198.51.100.1")
    file_sink(log)(old)  # before the flow: a confirmed download, not this flow's
    new = old.model_copy(update={"host": "198.51.100.2", "port": 80})

    async def worker_reaches_out(_pids: Sequence[int]) -> str:
        if len(read_records(log)) == 1:
            file_sink(log)(new)
        return ""

    report = check(worker, tmp_path, sampler=worker_reaches_out)

    assert [f.host for f in report.findings] == ["198.51.100.2"]
    finding = report.findings[0]
    assert (finding.source, finding.process, finding.port) == ("audit", "worker", 80)
    assert not report.passed


def test_us_12_4_lsof_connection_is_caught(worker: EvalWorker, tmp_path: Path) -> None:
    async def telemetry(pids: Sequence[int]) -> str:
        return (
            f"p4242\ng{pids[0]}\nf9\nn10.0.0.5:50123->93.184.216.34:443\n"
            "p999\ng999\nf3\nn[::1]:5->[::1]:6\n"
        )

    async def worker_and_a_server() -> dict[int, str]:
        return {GROUP: "worker", 2_000_000_000: "model:drafting"}

    report = check(worker, tmp_path, sampler=telemetry, processes=worker_and_a_server)

    assert not report.passed
    assert report.observers["model:drafting:2000000000"] == ["lsof"]  # no audit in a server
    # A helper process of the worker's group (pid 4242) is attributed to the worker.
    assert {(f.source, f.process, f.pid, f.host, f.port) for f in report.findings} == {
        ("lsof", "worker", 4242, "93.184.216.34", 443)
    }
    lines = summarize(report)
    assert "BLOCKED" in lines[0]
    assert "  lsof worker:4242 connect 93.184.216.34:443" in lines


def test_us_12_4_a_stopped_flow_does_not_pass(worker: EvalWorker, tmp_path: Path) -> None:
    worker.servers[ModelRole.DRAFTING].replies.clear()
    worker.servers[ModelRole.DRAFTING].replies["default_model"] = "no letter"
    report = check(worker, tmp_path, sampler=lambda _pids: asyncio.sleep(0, ""))
    assert not report.flow_completed
    assert report.error_code == "drafting_failed"
    assert report.findings == []
    assert not report.passed
    assert "flow stopped (drafting_failed)" in summarize(report)[0]


def test_us_12_4_sampler_failure_stops_the_flow(worker: EvalWorker, tmp_path: Path) -> None:
    # Review finding: a broken lsof surfaced only after the whole flow.
    async def broken(_pids: Sequence[int]) -> str:
        raise EgressToolError

    with pytest.raises(EgressToolError):
        check(worker, tmp_path, sampler=broken)
    assert not EGRESS_AUDIT.active
    assert worker.servers[ModelRole.DRAFTING].requests == []  # the flow never got that far
    for listed in asyncio.run(worker.client().list_cases("default")).cases:
        case = asyncio.run(worker.client().get_case("default", listed.case_id))
        assert case.documents == []  # and its case was purged


def test_us_12_4_process_lookup_failure_is_a_tool_error(worker: EvalWorker, tmp_path: Path) -> None:
    async def lost() -> dict[int, str]:
        raise PermissionError("ps")

    with pytest.raises(EgressToolError):
        check(worker, tmp_path, processes=lost)


def test_us_12_4_one_sample_always_follows_the_flow(
    worker: EvalWorker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding: a flow ending during a sample skipped the sample after it.
    exported: list[bool] = []
    after_export: list[bool] = []
    real_export = GatewayDriver.export

    async def export(self: GatewayDriver, case_id: str) -> ExportedFile:
        file = await real_export(self, case_id)
        exported.append(True)
        return file

    async def slow(_pids: Sequence[int]) -> str:
        after_export.append(bool(exported))
        await asyncio.sleep(0.05)
        return ""

    monkeypatch.setattr(GatewayDriver, "export", export)
    report = check(worker, tmp_path, sampler=slow)
    assert report.passed
    assert after_export[-1], "the last sample follows the flow"
    # One sample after the export at least; under load a regular one may also land during the
    # purge that follows it (a timing flake when exactly one was required).
    assert after_export.count(True) >= 1


def test_us_12_4_worker_without_its_audit_is_not_measured(
    worker: EvalWorker, tmp_path: Path
) -> None:
    # Review finding: a worker started before this change has no hook; "no records" proves nothing.
    off = audit_answers(EgressStatus(audit=False, dropped=0))
    with pytest.raises(EgressAuditOffError, match="egress audit is not recording"):
        check(worker, tmp_path, worker_audit=off)
    assert asyncio.run(worker.client().list_cases("default")).cases == []


def test_us_12_4_unreadable_worker_log_is_not_measured(worker: EvalWorker, tmp_path: Path) -> None:
    # Tester observation: a log with mode 000 gave only "unexpected PermissionError".
    log = tmp_path / EGRESS_LOG
    log.write_text("")
    log.chmod(0)
    try:
        with pytest.raises(EgressLogError, match="cannot be read"):
            check(worker, tmp_path, sampler=lambda _p: asyncio.sleep(0, ""))
    finally:
        log.chmod(0o600)


def test_us_12_4_worker_log_that_cannot_be_statted_is_not_measured(
    worker: EvalWorker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stat = Path.stat

    def denied(self: Path, **kwargs: Any) -> os.stat_result:
        if self.name == EGRESS_LOG:
            raise PermissionError(13, "denied")
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", denied)
    with pytest.raises(EgressLogError):
        check(worker, tmp_path)


def test_us_12_4_records_the_worker_could_not_write_are_a_finding(
    worker: EvalWorker, tmp_path: Path
) -> None:
    lossy = audit_answers(EgressStatus(audit=True, dropped=2), EgressStatus(audit=True, dropped=3))
    report = check(worker, tmp_path, worker_audit=lossy, sampler=lambda _p: asyncio.sleep(0, ""))
    assert [(f.process, f.host) for f in report.findings] == [("worker", "unrecorded")]
    assert not report.passed


# --- lsof ----------------------------------------------------------------------------------------


def test_us_12_4_parse_lsof() -> None:
    output = "\n".join(
        [
            "p100",
            "g100",
            "f5",
            "n*:18200",  # listening
            "f6",
            "n127.0.0.1:18200->127.0.0.1:61000",
            "f7",
            "n[::1]:61001->[::1]:18201",
            "p200",
            "g100",
            "f3",
            "n192.168.1.4:5353",  # an unconnected datagram socket
            "f4",
            "n10.0.0.2:55000->140.82.112.3:https (ESTABLISHED)",
            "pnot-a-pid",
            "gnot-a-group",
            "nx->somehost",
            "nempty->",
        ]
    )
    assert parse_lsof(output) == [
        (100, 100, "127.0.0.1", 61000),
        (100, 100, "::1", 18201),
        (100, 200, "140.82.112.3", None),  # a child in the worker's group
        (100, 200, "somehost", None),
        (100, 200, "", None),  # unparseable: counted as non-loopback
    ]
    assert parse_lsof("p7\nn1.2.3.4:5->5.6.7.8:9") == [(7, 7, "5.6.7.8", 9)]


def test_us_12_4_sample_lsof_runs_lsof() -> None:
    assert asyncio.run(sample_lsof([])) == ""
    assert f"p{os.getpid()}" in asyncio.run(sample_lsof([GROUP])).splitlines()
    assert asyncio.run(sample_lsof([2_000_000_000])) == ""  # a group that is gone: rc 1, no error


@pytest.mark.parametrize(
    "outcome",
    [
        OSError("no lsof"),
        subprocess.TimeoutExpired(["lsof"], 15),
        subprocess.CompletedProcess(["lsof"], 2, "", "lsof: bad"),
        subprocess.CompletedProcess(["lsof"], 1, "", "lsof: WARNING: can't stat() /dev"),
    ],
)
def test_us_12_4_lsof_failure_is_an_error(
    outcome: BaseException | subprocess.CompletedProcess[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append({"argv": argv, **kwargs})
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("claimcoach.evals.egress_check.subprocess.run", run)
    with pytest.raises(EgressToolError, match="could not sample connections"):
        asyncio.run(sample_lsof([12, 34]))
    assert seen[0]["argv"] == ["/usr/sbin/lsof", "-nP", "-a", "-g", "12,34", "-i", "-F", "pgn"]
    assert seen[0]["stdin"] == subprocess.DEVNULL


# --- Preconditions and processes -----------------------------------------------------------------


def status(**changes: dict[str, Any]) -> ModelsStatusResponse:
    models = []
    for role in ModelRole:
        fields: dict[str, Any] = {
            "role": role,
            "state": "unloaded",
            "port": 18201,
            "tier_b": 8,
            "model_dir": "x",
            "weights": "present",
            "venv_present": True,
        }
        models.append(ModelStatus.model_validate(fields | changes.get(role.value, {})))
    return ModelsStatusResponse(idle_timeout_s=600, models=models)


def test_us_12_4_preconditions() -> None:
    assert preconditions(status()) == []
    assert preconditions(status(transcription={"weights": "missing"})) == []
    assert preconditions(
        status(
            drafting={"weights": "missing"},
            transcription={"acquire": "downloading", "weights": "missing"},
            embedding={"acquire": "failed"},
        )
    ) == ["drafting: weights missing", "transcription: downloading"]


def test_us_12_4_processes_are_the_worker_and_its_model_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = WorkerConfig(data_dir=tmp_path)
    answers: list[ModelsStatusResponse | None] = [
        status(classification={"state": "ready", "pid": 41}),
        None,
    ]

    class Status(WorkerClient):
        async def models_status(self) -> ModelsStatusResponse:
            answer = answers.pop(0)
            if answer is None:
                raise WorkerUnavailableError
            return answer

    handles: list[WorkerHandle | None] = [
        WorkerHandle(
            pid=7,
            base_url=config.base_url,
            token_path=config.token_path,
            started_at=NOW,
        ),
        None,
    ]
    monkeypatch.setattr(egress_check, "worker_status", lambda _config: handles.pop(0))
    current = app_processes(Status("http://worker", lambda: "t"), config)
    assert asyncio.run(current()) == {7: "worker", 41: "model:classification"}
    # The worker stopped answering: its model servers are still watched.
    assert asyncio.run(current()) == {41: "model:classification"}


# --- The audit hook ------------------------------------------------------------------------------


def recorder() -> tuple[EgressAudit, list[Callable[[str, tuple[object, ...]], None]]]:
    hooks: list[Callable[[str, tuple[object, ...]], None]] = []
    return EgressAudit(hooks.append), hooks


def test_us_12_4_audit_hook_is_added_once() -> None:
    audit, hooks = recorder()
    states = [audit.active]
    audit.start("worker", lambda _r: None)
    audit.start("plugin_api", lambda _r: None)
    states.append(audit.active)
    audit.stop()
    states.append(audit.active)
    assert len(hooks) == 1
    assert states == [False, True, False]


def test_us_12_4_audit_hook_keeps_only_non_loopback() -> None:
    audit, hooks = recorder()
    records: list[EgressRecord] = []
    audit.start("worker", records.append)
    (hook,) = hooks
    with (
        socket.socket(socket.AF_INET) as inet,
        socket.socket(socket.AF_UNIX) as unix,
    ):
        hook("open", ("/etc/hosts", "r", 0))
        hook("socket.connect", (inet, ("127.0.0.1", 18200)))
        hook("socket.connect", (inet, ("::1", 18200, 0, 0)))
        hook("socket.connect", (inet, ("localhost", 18200)))
        hook("socket.connect", (unix, "hermes.sock"))
        hook("socket.getaddrinfo", (None, 80, 0, 0, 0))
        hook("socket.getaddrinfo", (b"127.0.0.1", "80", 0, 0, 0))
        hook("socket.connect", (inet, ("192.0.2.10", 443)))
        hook("socket.sendto", (inet, ("192.0.2.11", 53)))
        hook("socket.getaddrinfo", (b"payer.example", b"443", 0, 0, 0))
        hook("socket.getaddrinfo", ("hub.example", "https", 0, 0, 0))
        hook("socket.connect", (inet, ("192.0.2.12",)))
        hook("socket.connect", (inet, "192.0.2.13"))
        hook("socket.getaddrinfo", ("hub.example", True, 0, 0, 0))
    audit.stop()
    hook("socket.connect", (inet, ("192.0.2.99", 443)))  # stopped: nothing more is kept
    assert [(r.event, r.host, r.port) for r in records] == [
        ("connect", "192.0.2.10", 443),
        ("sendto", "192.0.2.11", 53),
        ("resolve", "payer.example", 443),
        ("resolve", "hub.example", None),
        ("connect", "192.0.2.12", None),
        ("connect", "192.0.2.13", None),
        ("resolve", "hub.example", None),
    ]
    assert {r.process for r in records} == {"worker"}
    assert {r.pid for r in records} == {os.getpid()}


def test_us_12_4_a_failing_sink_never_breaks_the_socket_call() -> None:
    # Review finding: a full disk made the worker's own connect() raise from the hook.
    audit, hooks = recorder()

    def full(_record: EgressRecord) -> None:
        raise OSError(28, "No space left on device")

    audit.start("worker", full)
    with socket.socket(socket.AF_INET) as inet:
        hooks[0]("socket.connect", (inet, ("192.0.2.10", 443)))
        hooks[0]("socket.connect", (inet, ("127.0.0.1", 443)))
    assert audit.dropped == 1
    assert audit.status() == EgressStatus(audit=True, dropped=1)


def test_us_12_4_a_failed_report_write_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = EgressReport(
        started_at=NOW,
        finished_at=NOW,
        flow_completed=True,
        processes=[],
        observers={},
        samples=1,
        findings=[],
        passed=True,
    )

    def full(_self: Path, _target: Path) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "replace", full)
    with pytest.raises(OSError, match="No space"):
        write_report(report, tmp_path, "egress.json")
    assert list((tmp_path / "US-12.4").iterdir()) == []


def test_us_12_4_record_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / EGRESS_LOG
    record = EgressRecord(at=NOW, process="worker", pid=1, event="connect", host="192.0.2.1")
    file_sink(path)(record)
    file_sink(path)(record.model_copy(update={"port": 443}))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    first_line = len(path.read_bytes().splitlines()[0]) + 1
    assert read_records(path) == [record, record.model_copy(update={"port": 443})]
    assert read_records(path, first_line) == [record.model_copy(update={"port": 443})]
    with pytest.raises(FileNotFoundError):  # a missing folder shows when the sink is made
        file_sink(tmp_path / "missing" / EGRESS_LOG)


def test_us_12_4_unreadable_records_still_count(tmp_path: Path) -> None:
    path = tmp_path / EGRESS_LOG
    assert read_records(path) == []
    path.write_bytes(b'\n{"torn": \n\n')
    (record,) = read_records(path)
    assert (record.host, record.process) == ("unreadable", "unknown")


def test_us_12_4_worker_starts_the_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    audit, _hooks = recorder()
    served: list[dict[str, Any]] = []

    def serve(_app: object, **kwargs: Any) -> None:
        started.append("serving")
        served.append(kwargs)

    monkeypatch.setattr(uvicorn, "run", serve)

    def start(process: str, sink: Callable[[EgressRecord], None]) -> None:
        started.append(process)
        audit.start(process, sink)

    monkeypatch.setattr(EGRESS_AUDIT, "start", start)
    assert worker_main.main(["--data-dir", str(tmp_path), "--port", "18201"]) == 0
    assert started == ["worker", "serving"]  # before the registry loads and before serving
    assert served[0]["loop"] == "asyncio"  # uvloop's sockets raise no audit events
    record = EgressRecord(at=NOW, process="worker", pid=1, event="connect", host="192.0.2.1")
    assert audit._sink is not None
    audit._sink(record)
    assert read_records(tmp_path / "worker" / EGRESS_LOG) == [record]


def test_us_12_4_worker_without_a_record_file_serves_with_the_audit_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_file(_path: Path) -> Callable[[EgressRecord], None]:
        raise PermissionError("read-only")

    started: list[str] = []
    monkeypatch.setattr(worker_main, "file_sink", no_file)
    monkeypatch.setattr(EGRESS_AUDIT, "start", lambda *_a: started.append("audit"))
    monkeypatch.setattr(uvicorn, "run", lambda _app, **_kw: started.append("serving"))
    assert worker_main.main(["--data-dir", str(tmp_path), "--port", "18201"]) == 0
    assert started == ["serving"]


def test_us_12_4_worker_reports_its_audit() -> None:
    app = create_app(TOKEN)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    assert asyncio.run(client.egress_status()) == EGRESS_AUDIT.status()
    response = asyncio.run(
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://w").get("/egress")
    )
    assert response.status_code == 401  # the bearer gate covers it


# --- The gateway driver --------------------------------------------------------------------------


def test_us_12_4_gateway_refusals_are_error_codes(worker: EvalWorker) -> None:
    async def go() -> list[str]:
        codes: list[str] = []
        async with gateway_driver(worker.client()) as gateway:
            await gateway.create_case()
            for call in (
                gateway.open_case("case_0123456789abcdef"),
                gateway.paste("not-a-case-id!", "x"),
            ):
                try:
                    await call
                except FlowError as exc:
                    codes.append(exc.code)
        return codes

    assert asyncio.run(go()) == ["case_not_found", "invalid_request"]


def test_us_12_4_gateway_non_envelope_failure_is_worker_error() -> None:
    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>oops</html>")

    async def go() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(broken), base_url="http://plugin-api"
        ) as http:
            gateway = GatewayDriver(http=http, worker=None)  # type: ignore[arg-type]
            await gateway.create_case()

    with pytest.raises(FlowError) as raised:
        asyncio.run(go())
    assert raised.value.code == "worker_error"


def test_us_12_4_gateway_job_that_never_ends_times_out(worker: EvalWorker) -> None:
    async def go() -> None:
        async with gateway_driver(worker.client()) as gateway:
            gateway.job_wait = 0.01
            gateway.sink = lambda *_args: None  # type: ignore[method-assign]
            case_id = await gateway.create_case()
            await gateway.paste(case_id, DENIAL_SET.cases[0].documents[0].text)
            await gateway.run_job(case_id, "extract")

    with pytest.raises(FlowError) as raised:
        asyncio.run(go())
    assert raised.value.code == "processing_timeout"


# --- The CLI -------------------------------------------------------------------------------------


@pytest.fixture
def managed(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[EvalWorker]:
    """The eval worker with a model manager, so ``/models/status`` answers."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    env = build_model_env(tmp_path)
    with eval_worker(tmp_path / "hermes", corpus_server, models=env.manager()) as served:
        yield served


def run_cli(tmp_path: Path, worker: EvalWorker, *extra: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    argv = ["egress", "--set", str(FIXTURE_PATH), "--out", str(tmp_path / "evidence"), *extra]
    code = main(
        argv,
        out=lines.append,
        connect=connect_to(worker),
        config_for=lambda port: WorkerConfig(data_dir=tmp_path / "data", port=port),
    )
    return code, lines


def test_us_12_4_cli_writes_the_report(
    tmp_path: Path, managed: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding: the CLI path must really watch the worker it found (here: this test's group).
    handle = WorkerHandle(
        pid=GROUP, base_url="http://127.0.0.1:18200", token_path=tmp_path / "t", started_at=NOW
    )
    monkeypatch.setattr(egress_check, "worker_status", lambda _config: handle)
    code, lines = run_cli(tmp_path, managed)
    assert code == 0, lines
    report = EgressReport.model_validate_json((tmp_path / "evidence" / REPORT).read_text())
    assert report.passed
    assert f"worker:{GROUP}" in report.processes
    assert report.samples >= 2
    assert lines[0].startswith("US-12.4 egress: flow completed, ")
    assert lines[0].endswith("0 non-loopback: PASS")


def test_us_12_4_cli_blocks_on_a_finding(
    tmp_path: Path, managed: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = run_egress_check

    async def with_finding(*args: Any, **kwargs: Any) -> tuple[EgressReport, list[str]]:
        report, kept = await real(*args, **kwargs)
        finding = EgressFinding(
            source="audit", process="worker", pid=1, event="resolve", host="hub.example"
        )
        return report.model_copy(update={"findings": [finding], "passed": False}), kept

    monkeypatch.setattr(evals_main, "run_egress_check", with_finding)
    code, lines = run_cli(tmp_path, managed)
    assert code == 1
    assert "  audit worker:1 resolve hub.example" in lines


def test_us_12_4_cli_needs_every_case_model(tmp_path: Path, managed: EvalWorker) -> None:
    weights = next((tmp_path / "Models").rglob("model.safetensors"))
    role_dir = weights.parent
    for path in role_dir.iterdir():
        path.unlink()
    code, lines = run_cli(tmp_path, managed)
    assert code == 2
    assert any(line.startswith("not measured: ") and "weights missing" in line for line in lines)
    assert not (tmp_path / "evidence" / REPORT).exists()


def test_us_12_4_cli_unknown_case(tmp_path: Path, managed: EvalWorker) -> None:
    code, lines = run_cli(tmp_path, managed, "--case", "denial_999")
    assert code == 2
    assert lines == [f"not measured: no case denial_999 in {FIXTURE_PATH}"]


def test_us_12_4_cli_named_case_and_lsof_failure(
    tmp_path: Path, managed: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_lsof(*_args: Any, **_kwargs: Any) -> EgressReport:
        raise EgressToolError

    monkeypatch.setattr(evals_main, "run_egress_check", no_lsof)
    code, lines = run_cli(tmp_path, managed, "--case", "denial_001")
    assert code == 2
    assert lines == ["not measured: /usr/sbin/lsof could not sample connections"]


def test_us_12_4_cli_refuses_a_worker_without_its_audit(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    env = build_model_env(tmp_path)
    off = EgressStatus(audit=False, dropped=0)
    with eval_worker(
        tmp_path / "hermes", corpus_server, models=env.manager(), egress=off
    ) as served:
        code, lines = run_cli(tmp_path, served)
    assert code == 2
    assert lines == [
        "not measured: the worker's egress audit is not recording; restart it (make stop, "
        "make start)"
    ]


def test_us_12_4_cli_names_an_unpurged_case(
    tmp_path: Path, managed: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(*_args: object) -> None:
        raise WorkerUnavailableError

    monkeypatch.setattr(WorkerDriver, "discard", refuse)
    _code, lines = run_cli(tmp_path, managed)
    (warning,) = [line for line in lines if line.startswith("warning: ")]
    assert warning.startswith("warning: eval case case_")
    assert warning.endswith("CONFIRM=yes")


def test_us_12_4_cli_worker_failure_is_not_measured(tmp_path: Path, worker: EvalWorker) -> None:
    code, lines = run_cli(tmp_path, worker)  # no model manager: /models/status is not served
    assert code == 2
    assert lines == ["not measured: the worker answered worker_error"]


def test_us_12_4_cli_no_worker(tmp_path: Path) -> None:
    lines: list[str] = []
    client = WorkerClient("http://127.0.0.1:18219", lambda: None)
    argv = ["egress", "--set", str(FIXTURE_PATH), "--out", str(tmp_path)]
    assert main(argv, out=lines.append, connect=lambda _port: client) == 2
    assert lines[0].endswith("answered worker_unavailable")


def test_us_12_4_cli_watches_the_worker_of_this_data_dir() -> None:
    config = evals_main._config(18205)
    assert (config.data_dir, config.port) == (app_data_dir(), 18205)


def test_us_12_4_egress_case_is_the_first_with_a_pdf() -> None:
    assert PDF_CASE is not None
    assert PDF_CASE.id == "denial_003"
    no_pdf = DENIAL_SET.model_copy(update={"cases": DENIAL_SET.cases[:2]})
    assert pick_egress_case(no_pdf, None) == DENIAL_SET.cases[0]
    assert pick_egress_case(DENIAL_SET, "denial_002") == DENIAL_SET.cases[1]


# --- Real app ------------------------------------------------------------------------------------


@pytest.mark.models
def test_us_12_4_full_flow_on_the_running_app(tmp_path: Path) -> None:
    port = running_worker_port()
    lines: list[str] = []
    argv = ["egress", "--set", str(FIXTURE_PATH), "--out", str(tmp_path), "--port", str(port)]
    code = main(argv, out=lines.append)
    report = EgressReport.model_validate_json((tmp_path / REPORT).read_text())
    assert code == 0, "\n".join(lines)
    assert report.passed
    assert any(name.startswith("worker:") for name in report.processes)
    assert any(name.startswith("model:") for name in report.processes)
