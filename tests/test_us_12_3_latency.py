"""US-12.3 Upload-to-Draft Latency Measurement.

Scenario: the latency benchmark reports the median. Also: the gate above 10 minutes, failed cases
in the median, the benchmark mix and ``--limit``, the step times, the flow driver's failures (a
failed job, a job that never ends, a refused upload, a case that cannot be created or purged), and
the EOB PDF renderer. The real-model benchmark is under the ``models`` marker.
Rules: ES-4, ES-5, NFR-3, BR-7, BR-12, BR-14.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable, Iterator
from pathlib import Path

import pymupdf
import pytest

from claimcoach.api.client import WorkerClient, WorkerRejectedError, WorkerUnavailableError
from claimcoach.cases.extraction import JobEvents, JobStarted
from claimcoach.evals.__main__ import main
from claimcoach.evals.flow import FlowError, WorkerDriver, pdf_of, run_case
from claimcoach.evals.latency import benchmark_cases, median_seconds, run_latency
from claimcoach.evals.report import summarize
from claimcoach.evals.types import LATENCY_TARGET_SECONDS, CaseTiming, LatencyReport, exit_code
from claimcoach.events import CaseProgressEvent
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from tests.fakes.evals import DENIAL_SET, EvalWorker, connect_to, eval_worker, running_worker_port
from tests.fakes.fake_model_server import FakeModelServer
from tests.fixtures.denials.generate import FIXTURE_PATH

REPORT = Path("US-12.3") / "latency.json"
CASE = DENIAL_SET.cases[0]


@pytest.fixture
def worker(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[EvalWorker]:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    with eval_worker(tmp_path / "hermes", corpus_server) as served:
        yield served


def ticking(step: float) -> Callable[[], float]:
    """A monotonic clock that advances ``step`` seconds per reading."""
    counter = itertools.count()
    return lambda: next(counter) * step


def driver_for(worker: EvalWorker, **kwargs: object) -> WorkerDriver:
    return WorkerDriver(worker.client(), "default", **kwargs)  # type: ignore[arg-type]


# --- Scenario: Latency benchmark reports the median ----------------------------------------------


def test_us_12_3_latency_reports_median(tmp_path: Path, worker: EvalWorker) -> None:
    lines: list[str] = []
    argv = ["latency", "--set", str(FIXTURE_PATH), "--out", str(tmp_path), "--limit", "6"]
    code = main(argv, out=lines.append, connect=connect_to(worker))

    assert code == 0
    report = LatencyReport.model_validate_json((tmp_path / REPORT).read_text())
    assert report.passed
    assert report.target_seconds == LATENCY_TARGET_SECONDS == 600
    assert report.median_seconds is not None
    assert report.median_seconds <= LATENCY_TARGET_SECONDS
    assert len(report.cases) == 6
    assert {kind for case in report.cases for kind in case.kinds} == {
        "era_835",
        "letter",
        "eob_pdf",
    }
    for timing in report.cases:
        assert timing.seconds is not None
        assert timing.stages is not None
        assert timing.error_code is None
        stages = timing.stages
        total = stages.upload + stages.extract + stages.diagnose + stages.draft
        assert total == pytest.approx(timing.seconds)
    assert lines[0].startswith("US-12.3 latency: median ")
    assert lines[0].endswith("over 6 cases, target 600 s: PASS")


def test_us_12_3_median_over_target_blocks(worker: EvalWorker) -> None:
    # Each step "takes" 200 s: upload, extract, diagnose, draft = 800 s per case.
    three = DENIAL_SET.model_copy(update={"cases": DENIAL_SET.cases[:3]})
    report, kept = asyncio.run(run_latency(driver_for(worker), three, clock=ticking(200)))
    assert kept == []
    assert report.median_seconds == 800
    assert not report.passed
    assert exit_code(report.passed) == 1
    assert {t.stages.draft for t in report.cases if t.stages} == {200}
    assert "BLOCKED" in summarize(report)[0]


def test_us_12_3_failed_cases_count_as_slowest() -> None:
    def timing(seconds: float | None) -> CaseTiming:
        return CaseTiming(case="c", kinds=["era_835"], seconds=seconds)

    assert median_seconds([timing(10), timing(None), timing(30)]) == 30
    assert median_seconds([timing(10), timing(20), timing(30), timing(None)]) == 25
    assert median_seconds([timing(10), timing(None)]) is None
    assert median_seconds([timing(None)]) is None


def test_us_12_3_a_failed_case_fails_the_gate(worker: EvalWorker) -> None:
    worker.servers[ModelRole.DRAFTING].replies[DEFAULT_MODEL_ID] = "no letter here"
    one = DENIAL_SET.model_copy(update={"cases": DENIAL_SET.cases[:1]})
    report, _kept = asyncio.run(run_latency(driver_for(worker), one))
    assert not report.passed
    assert report.median_seconds is None
    (timing,) = report.cases
    assert (timing.seconds, timing.stages, timing.error_code) == (None, None, "drafting_failed")
    lines = summarize(report)
    assert "median unbounded over 1 cases" in lines[0]
    assert lines[1].endswith("drafting_failed")


def test_us_12_3_benchmark_mixes_document_kinds() -> None:
    picked = benchmark_cases(DENIAL_SET)
    assert len(picked) == len(DENIAL_SET.cases)
    assert [c.kinds[0] for c in picked[:6]] == ["era_835", "letter", "eob_pdf"] * 2
    assert [c.id for c in benchmark_cases(DENIAL_SET, 2)] == ["denial_001", "denial_002"]


# --- The flow driver -----------------------------------------------------------------------------


def test_us_12_3_flow_stops_at_the_diagnosis(worker: EvalWorker) -> None:
    result = asyncio.run(run_case(driver_for(worker), CASE, until="diagnose"))
    assert result.discarded
    assert result.case is not None
    assert result.case.diagnosis is not None
    assert result.case.draft is None
    assert result.stages is not None
    assert result.stages.draft == 0
    assert result.exported is None


def test_us_12_3_flow_exports_the_draft(worker: EvalWorker) -> None:
    result = asyncio.run(run_case(driver_for(worker), DENIAL_SET.cases[2], until="export"))
    assert result.error_code is None
    assert result.exported is not None
    assert result.exported.format == "pdf"
    assert result.case is not None
    assert result.case.draft is not None


def test_us_12_3_job_that_never_ends_times_out() -> None:
    started = JobStarted(case_id="case_0123456789abcdef", job_id="job_0123456789abcdef")

    class Stuck(WorkerClient):
        async def start_extraction(self, *_args: object) -> JobStarted:
            return started

        async def job_events(self, *_args: object) -> JobEvents:
            return JobEvents(job_id=started.job_id, events=[], finished=False)

    driver = WorkerDriver(
        Stuck("http://worker", lambda: "t"), "default", job_wait=10, clock=ticking(4)
    )
    with pytest.raises(FlowError) as raised:
        asyncio.run(driver.run_job(started.case_id, "extract"))
    assert raised.value.code == "processing_timeout"


@pytest.mark.parametrize(
    ("events", "code"),
    [
        ([], "worker_error"),
        ([("failed", "extraction_failed")], "extraction_failed"),
        ([("failed", None)], "worker_error"),
        ([("extracting", None)], "worker_error"),
    ],
)
def test_us_12_3_a_finished_job_that_did_not_succeed_fails(
    events: list[tuple[str, str | None]], code: str
) -> None:
    started = JobStarted(case_id="case_0123456789abcdef", job_id="job_0123456789abcdef")
    page = JobEvents(
        job_id=started.job_id,
        events=[
            CaseProgressEvent.model_validate(
                {
                    "case_id": started.case_id,
                    "job_id": started.job_id,
                    "stage": stage,
                    "progress": 1,
                    "error_code": error,
                }
            )
            for stage, error in events
        ],
        finished=True,
    )

    class Finished(WorkerClient):
        async def start_draft(self, *_args: object) -> JobStarted:
            return started

        async def job_events(self, *_args: object) -> JobEvents:
            return page

    driver = WorkerDriver(Finished("http://worker", lambda: "t"), "default")
    with pytest.raises(FlowError) as raised:
        asyncio.run(driver.run_job(started.case_id, "draft"))
    assert raised.value.code == code


def test_us_12_3_refused_step_is_its_error_code(
    worker: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(*_args: object) -> None:
        raise WorkerRejectedError("unsupported_document")

    monkeypatch.setattr(WorkerDriver, "upload", refuse)
    result = asyncio.run(run_case(driver_for(worker), DENIAL_SET.cases[1], until="draft"))
    assert result.error_code == "unsupported_document"
    assert result.discarded
    assert result.seconds is None


def test_us_12_3_no_case_means_nothing_to_purge() -> None:
    driver = WorkerDriver(WorkerClient("http://127.0.0.1:18219", lambda: None), "default")
    result = asyncio.run(run_case(driver, CASE, until="draft"))
    assert (result.error_code, result.discarded, result.case) == ("worker_unavailable", False, None)


@pytest.mark.parametrize("error", [WorkerUnavailableError(), RuntimeError("store locked")])
def test_us_12_3_purge_failure_is_reported(
    worker: EvalWorker, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    async def refuse(_self: WorkerDriver, _case_id: str) -> None:
        raise error

    monkeypatch.setattr(WorkerDriver, "discard", refuse)
    result = asyncio.run(run_case(driver_for(worker), CASE, until="diagnose"))
    assert result.case is not None
    assert result.case_id == result.case.case_id
    assert not result.discarded


def test_us_12_3_benchmark_names_unpurged_cases(
    worker: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(_self: WorkerDriver, _case_id: str) -> None:
        raise WorkerUnavailableError

    monkeypatch.setattr(WorkerDriver, "discard", refuse)
    two = DENIAL_SET.model_copy(update={"cases": DENIAL_SET.cases[:2]})
    report, kept = asyncio.run(run_latency(driver_for(worker), two))
    assert report.passed
    assert len(kept) == 2
    assert all(case_id.startswith("case_") for case_id in kept)


def test_us_12_3_unexpected_step_failure_is_a_code_and_still_purged(
    worker: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding: a ValidationError (or any other error) skipped the purge.
    async def mismatch(_self: WorkerDriver, _case_id: str) -> None:
        raise RuntimeError("input_value={'payer_name': ...}")

    monkeypatch.setattr(WorkerDriver, "open_case", mismatch)
    result = asyncio.run(run_case(driver_for(worker), CASE, until="diagnose"))
    assert (result.error_code, result.discarded, result.case) == ("worker_error", True, None)
    assert result.case_id is not None
    case = asyncio.run(worker.client().get_case("default", result.case_id))
    assert case.documents == []


def test_us_12_3_cancelled_flow_purges_its_case(
    worker: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding: Ctrl-C between the draft and the purge left the case's content behind.
    started = asyncio.Event()

    async def hang(_self: WorkerDriver, _case_id: str, _kind: str) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(WorkerDriver, "run_job", hang)
    driver = driver_for(worker)

    async def go() -> None:
        flow = asyncio.create_task(run_case(driver, CASE, until="draft"))
        await started.wait()
        flow.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flow

    asyncio.run(go())
    (listed,) = asyncio.run(worker.client().list_cases("default")).cases
    case = asyncio.run(worker.client().get_case("default", listed.case_id))
    assert case.documents == []


def test_us_12_3_eob_pdf_is_rendered_from_text() -> None:
    text = "\n".join(f"line {n}" for n in range(130))
    with pymupdf.open(stream=pdf_of(text), filetype="pdf") as document:  # type: ignore[no-untyped-call]
        assert document.page_count == 3
        assert "line 0" in document[0].get_text()
        assert "line 129" in document[2].get_text()
    with pymupdf.open(stream=pdf_of(""), filetype="pdf") as document:  # type: ignore[no-untyped-call]
        assert document.page_count == 1


# --- Real models ---------------------------------------------------------------------------------


@pytest.mark.models
def test_us_12_3_latency_on_this_mac(tmp_path: Path) -> None:
    port = running_worker_port()
    lines: list[str] = []
    argv = ["latency", "--set", str(FIXTURE_PATH), "--out", str(tmp_path), "--port", str(port)]
    code = main(argv, out=lines.append)
    report = LatencyReport.model_validate_json((tmp_path / REPORT).read_text())
    assert code == exit_code(report.passed), lines
    assert report.passed, "\n".join(lines)
