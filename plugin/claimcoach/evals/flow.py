"""Drive one eval case through the app: upload, extract, diagnose, draft, export, then purge.

Implements: US-12.2 (the classification eval reads the diagnosis a case reached), US-12.3 (each
step is timed from the first upload to the appeal-ready draft), US-12.4 (``GatewayDriver`` runs
the flow through the ``plugin_api`` router itself, in this process, so its audit hook watches the
gateway half's calls). Rules: PC-4 (every step is a REST call the pane also makes; nothing here
runs a model), BR-1 (loopback only: the worker on 127.0.0.1, the router in-process), BR-7 (every
eval case is purged when its flow ends, finished or not), BR-14 (a failure is kept as its error
code only).

``WorkerDriver`` waits on a job by long-polling the worker's job events; ``GatewayDriver`` waits on
the ``case.progress`` events the router's relay publishes, exactly as the pane does.
"""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
import secrets
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol, TypeVar

import httpx
import pymupdf
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api import routes
from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import ErrorCode, ErrorEnvelope
from claimcoach.cases.extraction import JOB_DEADLINE, JobKind, JobStarted
from claimcoach.cases.models import Case, DocumentAdded, PastedText
from claimcoach.corpus.paths import active_profile
from claimcoach.corpus.types import PurgeRequest
from claimcoach.evals.datasets import DenialCase, DenialDocument
from claimcoach.evals.types import StageSeconds
from claimcoach.events import CaseProgressEvent
from claimcoach.letters.types import DraftRequest, ExportedFile, ExportFormat, ExportRequest

__all__ = [
    "GATEWAY_PREFIX",
    "CaseDriver",
    "FlowError",
    "FlowResult",
    "FlowStep",
    "GatewayDriver",
    "WorkerDriver",
    "gateway_driver",
    "multipart",
    "pdf_of",
    "run_case",
]

GATEWAY_PREFIX: Final = f"/api/plugins/{PLUGIN_NAME}"
"""Where Hermes mounts the ``plugin_api`` router."""
POLL_WAIT: Final = 20.0
"""Seconds each job-events poll may wait on the worker."""
JOB_WAIT: Final = JOB_DEADLINE + 300.0
"""Seconds an eval waits on one job: the worker's own deadline ends it first."""

FlowStep = Literal["diagnose", "draft", "export"]
"""Where a flow stops: the classification eval needs the diagnosis; the others go further."""
_TERMINAL: Final = frozenset({"done", "failed"})
_ACTIONS: Final[dict[JobKind, str]] = {
    "extract": "process",
    "diagnose": "diagnose",
    "draft": "draft",
}
_ALL_JOBS: Final[tuple[JobKind, ...]] = ("extract", "diagnose", "draft")
ModelT = TypeVar("ModelT", bound=BaseModel)


class FlowError(Exception):
    """A step of the flow failed; ``code`` says why (the worker's or the gateway's error code)."""

    def __init__(self, code: ErrorCode) -> None:
        """Keep the code only."""
        super().__init__(code)
        self.code: ErrorCode = code


class CaseDriver(Protocol):
    """What a flow needs from the app; ``WorkerDriver`` and ``GatewayDriver`` provide it."""

    async def create_case(self) -> str:
        """Create an empty case and return its ID."""

    async def paste(self, case_id: str, text: str) -> None:
        """Attach pasted text."""

    async def upload(self, case_id: str, filename: str, content_type: str, data: bytes) -> None:
        """Attach a file."""

    async def run_job(self, case_id: str, kind: JobKind) -> None:
        """Start a job and wait until it ends; raise ``FlowError`` unless it finished."""

    async def open_case(self, case_id: str) -> Case:
        """Read the case."""

    async def export(self, case_id: str) -> ExportedFile:
        """Export the case's draft as a PDF."""

    async def discard(self, case_id: str) -> None:
        """Purge the case now."""


def multipart(filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    """Build a one-file ``multipart/form-data`` body as the pane's upload sends it.

    Args:
        filename: The file's name (a fixed eval name, never a document's).
        content_type: Its declared media type.
        data: Its bytes.

    Returns:
        The body and its ``Content-Type`` header.
    """
    boundary = f"----claimcoach-eval-{secrets.token_hex(12)}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    return (
        head + data + f"\r\n--{boundary}--\r\n".encode(),
        f"multipart/form-data; boundary={boundary}",
    )


def pdf_of(text: str) -> bytes:
    """Render ``text`` onto US Letter pages, as a scanned EOB would arrive (a PDF to read)."""
    lines = text.splitlines() or [""]
    per_page = 60
    with pymupdf.open() as document:  # type: ignore[no-untyped-call]
        for start in range(0, len(lines), per_page):
            page = document.new_page(width=612, height=792)
            page.insert_text((36, 48), "\n".join(lines[start : start + per_page]), fontsize=9)
        data: bytes = document.tobytes()
    return data


async def _attach(driver: CaseDriver, case_id: str, document: DenialDocument) -> None:
    if document.kind == "era_835":
        await driver.paste(case_id, document.text)
    elif document.kind == "letter":
        await driver.upload(case_id, "denial-letter.txt", "text/plain", document.text.encode())
    else:
        await driver.upload(case_id, "eob.pdf", "application/pdf", pdf_of(document.text))


@dataclass(frozen=True)
class FlowResult:
    """What one case's flow reached.

    Attributes:
        case: The case as last read, once its last job finished.
        stages: Seconds per step, when the flow reached its last step.
        seconds: Upload to the last job's end (the draft, or the diagnosis), when it got there.
        exported: The export, when the flow went that far.
        error_code: Why the flow stopped early, when it did.
        case_id: The worker's ID of the eval case, once it was created.
        discarded: Whether the eval case was purged afterwards.
    """

    case: Case | None = None
    stages: StageSeconds | None = None
    seconds: float | None = None
    exported: ExportedFile | None = None
    error_code: ErrorCode | None = None
    case_id: str | None = None
    discarded: bool = False


async def _steps(
    driver: CaseDriver, case: DenialCase, case_id: str, until: FlowStep, clock: Callable[[], float]
) -> FlowResult:
    marks = [clock()]
    for document in case.documents:
        await _attach(driver, case_id, document)
    marks.append(clock())
    kinds: tuple[JobKind, ...] = ("extract", "diagnose") if until == "diagnose" else _ALL_JOBS
    for kind in kinds:
        await driver.run_job(case_id, kind)
        marks.append(clock())
    opened = await driver.open_case(case_id)
    exported = await driver.export(case_id) if until == "export" else None
    upload, extract, diagnose, *draft = (b - a for a, b in itertools.pairwise(marks))
    stages = StageSeconds(
        upload=upload, extract=extract, diagnose=diagnose, draft=draft[0] if draft else 0.0
    )
    return FlowResult(case=opened, stages=stages, seconds=marks[-1] - marks[0], exported=exported)


async def run_case(
    driver: CaseDriver,
    case: DenialCase,
    *,
    until: FlowStep,
    clock: Callable[[], float] = time.monotonic,
) -> FlowResult:
    """Run ``case`` through the app up to ``until``, then purge it whatever happened.

    Args:
        driver: How to reach the app.
        case: The eval case.
        until: The last step.
        clock: Monotonic seconds (tests).

    Returns:
        What the flow reached; a failed step is its error code, never an exception (an unexpected
        one is ``worker_error``). Only cancellation propagates, after the case is purged.
    """
    case_id: str | None = None
    try:
        case_id = await driver.create_case()
        result = await _steps(driver, case, case_id, until, clock)
    except (FlowError, WorkerError) as exc:
        result = FlowResult(error_code=exc.code)
    except asyncio.CancelledError:  # Ctrl-C, or the egress check stopping the flow
        if case_id is not None:
            await asyncio.shield(_discard(driver, case_id))
        raise
    except Exception:  # noqa: BLE001 - any other failure is one fixed code: its text may hold case data
        result = FlowResult(error_code="worker_error")
    if case_id is None:
        return result
    return dataclasses.replace(result, case_id=case_id, discarded=await _discard(driver, case_id))


async def _discard(driver: CaseDriver, case_id: str) -> bool:
    try:
        await driver.discard(case_id)
    except Exception:  # noqa: BLE001 - reported as a case left to purge, never as its text
        return False
    return True


def _failed(event: CaseProgressEvent | None) -> FlowError | None:
    if event is None or event.stage != "done":
        code: ErrorCode = (event.error_code if event else None) or "worker_error"
        return FlowError(code)
    return None


class WorkerDriver:
    """Run flows against the worker's REST API for one profile.

    Args:
        client: The worker client (``port_client`` for the running worker).
        profile: The Hermes profile whose user scope holds the eval cases.
        job_wait: Seconds to wait on one job at most.
        clock: Monotonic seconds (tests).
    """

    def __init__(
        self,
        client: WorkerClient,
        profile: str,
        *,
        job_wait: float = JOB_WAIT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep the client and the profile."""
        self.client = client
        self.profile = profile
        self._job_wait = job_wait
        self._clock = clock

    async def create_case(self) -> str:
        """Create an empty case."""
        return (await self.client.create_case(self.profile)).case_id

    async def paste(self, case_id: str, text: str) -> None:
        """Attach pasted text."""
        await self.client.paste_text(self.profile, case_id, PastedText(text=text))

    async def upload(self, case_id: str, filename: str, content_type: str, data: bytes) -> None:
        """Attach a file."""
        body, header = multipart(filename, content_type, data)
        await self.client.upload_document(self.profile, case_id, body, header)

    async def _start(self, case_id: str, kind: JobKind) -> JobStarted:
        if kind == "extract":
            return await self.client.start_extraction(self.profile, case_id)
        if kind == "diagnose":
            return await self.client.start_diagnosis(self.profile, case_id)
        return await self.client.start_draft(self.profile, case_id, DraftRequest())

    async def run_job(self, case_id: str, kind: JobKind) -> None:
        """Start the job and long-poll its events until it ends."""
        started = await self._start(case_id, kind)
        deadline = self._clock() + self._job_wait
        after, last = 0, None
        while self._clock() < deadline:
            page = await self.client.job_events(started.job_id, after, POLL_WAIT)
            after += len(page.events)
            last = page.events[-1] if page.events else last
            if page.finished:
                failure = _failed(last)
                if failure is not None:
                    raise failure
                return
        raise FlowError("processing_timeout")

    async def open_case(self, case_id: str) -> Case:
        """Read the case."""
        return await self.client.get_case(self.profile, case_id)

    async def export(self, case_id: str) -> ExportedFile:
        """Export the draft as a PDF."""
        request = ExportRequest(format=ExportFormat.PDF)
        return await self.client.export_draft(self.profile, case_id, request)

    async def discard(self, case_id: str) -> None:
        """Purge the case now (an eval case is never kept)."""
        request = PurgeRequest(profile=self.profile, case_id=case_id, confirm=True)
        await self.client.purge_corpus(request)


@dataclass
class GatewayDriver:
    """Run flows through the ``plugin_api`` router mounted in this process.

    Attributes:
        http: A client of the in-process gateway app.
        worker: Discards eval cases (the gateway has no purge route) for the active profile.
        job_wait: Seconds to wait on one job at most.
        events: The terminal ``case.progress`` event of each job, as the relay published it.
    """

    http: httpx.AsyncClient
    worker: WorkerDriver
    job_wait: float = JOB_WAIT
    events: dict[str, CaseProgressEvent] = field(default_factory=dict)
    _ended: dict[str, asyncio.Event] = field(default_factory=dict)

    def sink(self, _plugin: str, _event: str, payload: dict[str, Any]) -> None:
        """The router's event sink: note each job's terminal event."""
        event = CaseProgressEvent.model_validate(payload)
        if event.stage in _TERMINAL:
            self.events[event.job_id] = event
            self._ended.setdefault(event.job_id, asyncio.Event()).set()

    async def _call(  # noqa: PLR0913 - the one funnel: method, path, model, and the body
        self,
        method: str,
        path: str,
        model: type[ModelT],
        *,
        json: object = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> ModelT:
        response = await self.http.request(
            method, f"{GATEWAY_PREFIX}{path}", json=json, content=content, headers=headers
        )
        if response.status_code != httpx.codes.OK:
            try:
                raise FlowError(ErrorEnvelope.model_validate_json(response.content).error.code)
            except ValidationError:
                raise FlowError("worker_error") from None
        return model.model_validate_json(response.content)

    async def create_case(self) -> str:
        """Create an empty case."""
        return (await self._call("POST", "/cases", Case, json={})).case_id

    async def paste(self, case_id: str, text: str) -> None:
        """Attach pasted text."""
        await self._call("POST", f"/cases/{case_id}/paste", DocumentAdded, json={"text": text})

    async def upload(self, case_id: str, filename: str, content_type: str, data: bytes) -> None:
        """Attach a file."""
        body, header = multipart(filename, content_type, data)
        await self._call(
            "POST",
            f"/cases/{case_id}/documents",
            DocumentAdded,
            content=body,
            headers={"Content-Type": header},
        )

    async def run_job(self, case_id: str, kind: JobKind) -> None:
        """Press the job's button and wait for its terminal event."""
        started = await self._call(
            "POST", f"/cases/{case_id}/{_ACTIONS[kind]}", JobStarted, json={}
        )
        ended = self._ended.setdefault(started.job_id, asyncio.Event())
        try:
            await asyncio.wait_for(ended.wait(), self.job_wait)
        except TimeoutError:
            raise FlowError("processing_timeout") from None
        failure = _failed(self.events.get(started.job_id))
        if failure is not None:
            raise failure

    async def open_case(self, case_id: str) -> Case:
        """Read the case."""
        return await self._call("GET", f"/cases/{case_id}", Case)

    async def export(self, case_id: str) -> ExportedFile:
        """Export the draft as a PDF."""
        return await self._call(
            "POST", f"/cases/{case_id}/export", ExportedFile, json={"format": "pdf"}
        )

    async def discard(self, case_id: str) -> None:
        """Purge the case through the worker."""
        await self.worker.discard(case_id)


@asynccontextmanager
async def gateway_driver(client: WorkerClient) -> AsyncIterator[GatewayDriver]:
    """Mount the ``plugin_api`` router in this process, over ``client``, and drive it.

    Args:
        client: The worker client the router uses, as ``plugin_api`` does in the gateway.

    Yields:
        A driver whose calls go through the router; its relay publishes to the driver's sink.
    """
    app = FastAPI()
    app.include_router(routes.router, prefix=GATEWAY_PREFIX)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://plugin-api") as http:
        driver = GatewayDriver(http=http, worker=WorkerDriver(client, active_profile()))
        app.dependency_overrides[routes.get_worker_client] = lambda: client
        app.dependency_overrides[routes.get_event_sink] = lambda: driver.sink
        yield driver
