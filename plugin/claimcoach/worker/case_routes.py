"""Worker routes for cases and their source documents.

Implements: US-5.1 (``POST /cases``, ``GET /cases/{case_id}``, ``POST /cases/{case_id}/documents``
with the raw single-file multipart body, ``POST /cases/{case_id}/paste``), US-5.2 (``POST
/cases/{case_id}/extract`` starts a job, ``POST /cases/{case_id}/fields`` confirms a value, ``GET
/jobs/{job_id}/events`` long-polls a job's progress), US-6.1 (``POST /cases/{case_id}/diagnose``
starts a diagnosis job), US-7.1 (``POST /cases/{case_id}/draft`` starts a draft job), US-7.2
(``POST /cases/{case_id}/draft/text`` saves the biller's edits; ``POST /cases/{case_id}/export``
writes the stored draft as a PDF or DOCX file on this Mac). Rules: ES-8 (typed bodies; ``CaseError``
and ``CorpusError`` become their fixed envelopes in ``create_app``), BR-2 (case content reaches the
worker only from the gateway), BR-4 (no route sends, submits, or transmits anything: an export is a
file the biller saves; ``test_us_7_3_no_transmitting_route`` pins the route set), BR-14 (no content
is logged).

Store calls run off the event loop (``asyncio.to_thread`` or plain ``def`` routes): opening a user
store may prompt the Keychain, and sealing a 16 MiB file takes a moment.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request

from claimcoach.cases.extraction import FieldConfirmation, JobEvents, JobStarted
from claimcoach.cases.intake import parse_upload, read_limited
from claimcoach.cases.models import MAX_UPLOAD_BODY, Case, DocumentAdded, PastedText
from claimcoach.cases.service import CaseService
from claimcoach.corpus.types import DEFAULT_PROFILE, CaseId, ProfileName
from claimcoach.events import JOB_ID_PATTERN
from claimcoach.letters.draft import Drafter
from claimcoach.letters.export import Exports, render
from claimcoach.letters.types import DraftEdit, DraftRequest, ExportedFile, ExportRequest
from claimcoach.models.manager import ModelBusyError, ModelUnavailableError
from claimcoach.pipeline.jobs import MAX_WAIT, JobRegistry

__all__ = ["get_cases", "get_drafter", "get_exports", "get_jobs", "jobs_router", "router"]

router = APIRouter(prefix="/cases")
jobs_router = APIRouter(prefix="/jobs")


def get_cases(request: Request) -> CaseService:
    """Return the worker's case service (set by ``create_app``)."""
    return cast("CaseService", request.app.state.cases)


def get_jobs(request: Request) -> JobRegistry:
    """Return the worker's case jobs (set by ``create_app`` when it has a model provider).

    Raises:
        ModelUnavailableError: This worker runs without models, so nothing can be extracted or
            diagnosed.
    """
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise ModelUnavailableError
    return cast("JobRegistry", jobs)


def get_drafter(request: Request) -> Drafter:
    """Return the worker's drafter (set by ``create_app`` when it has a model provider).

    Raises:
        ModelUnavailableError: This worker runs without models, so nothing can be drafted.
    """
    drafter = getattr(request.app.state, "drafter", None)
    if drafter is None:
        raise ModelUnavailableError
    return cast("Drafter", drafter)


def get_exports(request: Request) -> Exports:
    """Return the worker's exports folder manager (set by ``create_app``)."""
    return cast("Exports", request.app.state.exports)


Cases = Annotated[CaseService, Depends(get_cases)]
Jobs = Annotated[JobRegistry, Depends(get_jobs)]
Drafters = Annotated[Drafter, Depends(get_drafter)]
ExportFiles = Annotated[Exports, Depends(get_exports)]
Profile = Annotated[ProfileName, Query()]
CasePath = Annotated[CaseId, Path()]


@router.post("", response_model=Case)
def create_case(cases: Cases, profile: Profile = DEFAULT_PROFILE) -> Case:
    """Create an open, empty case in ``profile``'s user scope."""
    return cases.create(profile)


@router.get("/{case_id}", response_model=Case)
def open_case(case_id: CasePath, cases: Cases, profile: Profile = DEFAULT_PROFILE) -> Case:
    """Return the case with its source documents (audited ``case_opened``)."""
    return cases.open(profile, case_id)


@router.post("/{case_id}/documents", response_model=DocumentAdded)
async def add_document(
    case_id: CasePath, request: Request, cases: Cases, profile: Profile = DEFAULT_PROFILE
) -> DocumentAdded:
    """Attach the one file of a ``multipart/form-data`` body (read in memory, never spooled)."""
    body = await read_limited(
        request.stream(), MAX_UPLOAD_BODY, request.headers.get("content-length")
    )
    upload = parse_upload(body, request.headers.get("content-type", ""))
    return await asyncio.to_thread(cases.add_file, profile, case_id, upload)


@router.post("/{case_id}/paste", response_model=DocumentAdded)
def paste(
    case_id: CasePath, body: PastedText, cases: Cases, profile: Profile = DEFAULT_PROFILE
) -> DocumentAdded:
    """Attach pasted text (``edi_835`` when it is an 835 interchange)."""
    return cases.add_text(profile, case_id, body.text)


@router.post("/{case_id}/extract", response_model=JobStarted)
async def extract(
    case_id: CasePath, cases: Cases, jobs: Jobs, profile: Profile = DEFAULT_PROFILE
) -> JobStarted:
    """Start extracting the case (or return the job already working on it)."""
    running = jobs.running(profile, case_id)
    if running is not None:
        return running
    await asyncio.to_thread(cases.check_extractable, profile, case_id)
    return jobs.start(profile, case_id)


@router.post("/{case_id}/diagnose", response_model=JobStarted)
async def diagnose(
    case_id: CasePath, cases: Cases, jobs: Jobs, profile: Profile = DEFAULT_PROFILE
) -> JobStarted:
    """Start diagnosing the extracted case (or return the job already working on it).

    A running job is returned before the case is checked: during the case's first extraction
    there is no extraction yet, and the biller follows that job instead of a refusal.
    """
    running = jobs.running(profile, case_id)
    if running is not None:
        return running
    await asyncio.to_thread(cases.check_diagnosable, profile, case_id)
    return jobs.start(profile, case_id, "diagnose")


@router.post("/{case_id}/draft", response_model=JobStarted)
async def draft(
    case_id: CasePath,
    jobs: Jobs,
    drafter: Drafters,
    body: DraftRequest | None = None,
    profile: Profile = DEFAULT_PROFILE,
) -> JobStarted:
    """Start drafting the diagnosed case's appeal letter (or return the job already running).

    Without a body the case's denial reason picks the letter template (US-7.1 decision 3).
    """
    running = jobs.running(profile, case_id)
    if running is not None:
        return running
    bound = drafter.for_request(body or DraftRequest())
    await asyncio.to_thread(bound.check, profile, case_id)
    return jobs.start(profile, case_id, "draft", runner=bound)


@router.post("/{case_id}/draft/text", response_model=Case)
async def edit_draft(
    case_id: CasePath,
    body: DraftEdit,
    cases: Cases,
    request: Request,
    profile: Profile = DEFAULT_PROFILE,
) -> Case:
    """Store the biller's text as the draft; refused while a draft job runs on the case.

    Raises:
        ModelBusyError: A draft job is running on the case; its save would replace the edit.
    """
    jobs = getattr(request.app.state, "jobs", None)
    running = None if jobs is None else cast("JobRegistry", jobs).running(profile, case_id)
    if running is not None and running.kind == "draft":
        raise ModelBusyError
    return await asyncio.to_thread(cases.edit_draft, profile, case_id, body)


@router.post("/{case_id}/export", response_model=ExportedFile)
async def export(
    case_id: CasePath,
    body: ExportRequest,
    cases: Cases,
    exports: ExportFiles,
    profile: Profile = DEFAULT_PROFILE,
) -> ExportedFile:
    """Write the stored draft as a PDF or DOCX file for the biller to save (US-7.2)."""

    def write() -> ExportedFile:
        data = render(cases.draft_of(profile, case_id), body.format)
        written = exports.write(profile, case_id, body.format, data)
        cases.record_export(profile, case_id)  # audited: case content left the encrypted store
        return written

    return await asyncio.to_thread(write)


@router.post("/{case_id}/fields", response_model=Case)
def confirm_field(
    case_id: CasePath, body: FieldConfirmation, cases: Cases, profile: Profile = DEFAULT_PROFILE
) -> Case:
    """Store the biller's value for one field as confirmed."""
    return cases.confirm_field(profile, case_id, body)


@jobs_router.get("/{job_id}/events", response_model=JobEvents)
async def job_events(
    job_id: Annotated[str, Path(pattern=JOB_ID_PATTERN)],
    jobs: Jobs,
    after: Annotated[int, Query(ge=0)] = 0,
    wait: Annotated[float, Query(ge=0, le=MAX_WAIT)] = 0.0,
) -> JobEvents:
    """Return the job's progress events after ``after``, waiting up to ``wait`` seconds."""
    return await jobs.events(job_id, after, wait)
