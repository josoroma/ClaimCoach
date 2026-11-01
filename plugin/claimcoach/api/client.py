"""The single httpx client the gateway uses to reach the worker.

Implements: US-1.3 (one ``WorkerClient`` with typed methods; ``httpx.HTTPError`` and
``ValidationError`` caught explicitly, no bare ``except``), US-2.2 and US-2.4 (model status,
download, and conversion calls; the worker's own model error codes reach the desktop half), US-3.2
(``redact`` for the agent-tool guard), US-4.1 to US-4.6 (corpus status, import, view,
reindex, purge, and audit calls for the ``hermes claimcoach corpus`` command), US-5.1 (case
creation, open, upload, and paste calls; an upload is forwarded as the raw multipart body), US-5.2
(start extraction, long-poll a job's events, confirm a field), US-6.1 (start a diagnosis), US-7.1
(start a draft), US-7.2 (save the biller's edits, export the draft to a file on this Mac), US-8.1
(record a case's outcome), US-8.2 (the manager's weekly summary), US-8.3 (the manager-approved
fine-tune export), US-9.1 (explain a code, a payer's rule cards), US-9.2 (a case's redacted
summary), all for the agent tools.
Rules: ES-1, ES-8, PC-4 (the gateway only proxies; heavy work runs in the worker), BR-14 (a relayed
error keeps only its code; the message is the fixed one for that code).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Literal, NamedTuple, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from claimcoach.agent.types import (
    CaseSummaryParams,
    CaseSummaryResult,
    ExplainCodeParams,
    ExplainCodeResult,
    PayerRulesParams,
    PayerRulesResult,
)
from claimcoach.api.models import ErrorCode, ErrorEnvelope, HealthResponse
from claimcoach.cases.extraction import FieldConfirmation, JobEvents, JobStarted
from claimcoach.cases.models import Case, DocumentAdded, OutcomeRequest, PastedText
from claimcoach.corpus.bundle import CorpusBundle, CorpusViewResponse, ImportResult
from claimcoach.corpus.types import (
    AuditResponse,
    CorpusStatusResponse,
    PurgeRequest,
    PurgeResponse,
    ReindexRequest,
    ReindexResult,
)
from claimcoach.letters.types import DraftEdit, DraftRequest, ExportedFile, ExportRequest
from claimcoach.models.types import (
    AcquireResult,
    ConversionRequest,
    DownloadRequest,
    ModelsStatusResponse,
)
from claimcoach.outcomes.types import FineTuneExport, FineTuneExportRequest, WeeklySummary
from claimcoach.redact.types import RedactRequest, RedactResponse

__all__ = [
    "CASE_TIMEOUT",
    "POLL_TIMEOUT",
    "RELAYED_CODES",
    "InvalidWorkerResponseError",
    "RawBody",
    "WorkerClient",
    "WorkerError",
    "WorkerFailedError",
    "WorkerRejectedError",
    "WorkerUnauthorizedError",
    "WorkerUnavailableError",
]

ModelT = TypeVar("ModelT", bound=BaseModel)

RELAYED_CODES: Final[dict[ErrorCode, int]] = {
    "invalid_request": 422,
    "model_unavailable": 503,
    "model_busy": 409,
    "conversion_unavailable": 409,
    "corpus_unavailable": 503,
    "index_stale": 409,
    "case_not_found": 404,
    "profile_not_found": 404,
    "document_too_large": 413,
    "unsupported_document": 415,
    "case_closed": 409,
    "no_documents": 409,
    "job_not_found": 404,
    "not_extracted": 409,
    "not_diagnosed": 409,
    "no_letter_template": 409,
    "not_drafted": 409,
    "export_not_approved": 403,
    "code_not_found": 404,
    "payer_not_found": 404,
}
"""Worker error codes the desktop half acts on, with the status the gateway answers them with."""

CASE_TIMEOUT: Final = 60.0
"""Seconds per case call: the first one may wait on a Keychain prompt, an upload seals 16 MiB."""
POLL_TIMEOUT: Final = 35.0
"""Seconds per job-events poll: longer than the worker's longest wait (25 s)."""


class RawBody(NamedTuple):
    """A request body forwarded as received (an upload's multipart body)."""

    content: bytes
    content_type: str


class WorkerError(Exception):
    """A worker call failed; ``code`` and ``status_code`` say how to answer the desktop half."""

    code: ErrorCode = "worker_error"
    status_code: int = 502


class WorkerUnavailableError(WorkerError):
    """The worker is not running, not reachable, or has not issued a token yet."""

    code = "worker_unavailable"
    status_code = 503


class WorkerUnauthorizedError(WorkerError):
    """The worker rejected the bearer token."""

    code = "unauthorized"
    status_code = 401


class WorkerFailedError(WorkerError):
    """The worker answered with an error status."""

    code = "worker_error"
    status_code = 502


class WorkerRejectedError(WorkerError):
    """The worker refused the request with one of ``RELAYED_CODES``."""

    def __init__(self, code: ErrorCode) -> None:
        """Keep the worker's code and its gateway status; never the worker's message."""
        super().__init__(code)
        self.code = code
        self.status_code = RELAYED_CODES[code]


class InvalidWorkerResponseError(WorkerError):
    """The worker answered 2xx with a body that does not match the expected model."""

    code = "invalid_worker_response"
    status_code = 502


class WorkerClient:
    """Typed calls to the worker's HTTP API.

    Args:
        base_url: Root URL of the worker, e.g. ``http://127.0.0.1:18200``.
        token_provider: Returns the current per-launch token, or ``None`` before the first launch.
            Called on every request because the token changes on every worker start.
        transport: Optional httpx transport (tests pass an ``ASGITransport``).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        token_provider: Callable[[], str | None],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Store the connection settings; no connection is opened until a call."""
        self._base_url = base_url
        self._token_provider = token_provider
        self._transport = transport
        self._timeout = timeout

    async def health(self) -> HealthResponse:
        """Return the worker's health.

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/health", HealthResponse)

    async def models_status(self) -> ModelsStatusResponse:
        """Return the status of every model role.

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/models/status", ModelsStatusResponse)

    async def download_model(self, request: DownloadRequest) -> AcquireResult:
        """Ask the worker to download a role's model (only runs when ``confirm`` is true).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/models/download", AcquireResult, request)

    async def convert_model(self, request: ConversionRequest) -> AcquireResult:
        """Ask the worker to convert a role's model locally (only when ``confirm`` is true).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/models/convert", AcquireResult, request)

    async def redact(self, request: RedactRequest) -> RedactResponse:
        """Ask the worker to redact a text with its local PHI model and validators.

        Raises:
            WorkerError: The call failed; the subclass names why. No text is returned then.
        """
        return await self._request("POST", "/redact", RedactResponse, request)

    async def corpus_status(self) -> CorpusStatusResponse:
        """Return both corpus scopes' status (US-4.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/corpus/status", CorpusStatusResponse)

    async def import_corpus(self, bundle: CorpusBundle) -> ImportResult:
        """Import a bundle into the global scope (US-4.3).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing is stored then.
        """
        return await self._request("POST", "/corpus/import", ImportResult, bundle)

    async def corpus_view(self) -> CorpusViewResponse:
        """Return the global corpus view with provenance (US-4.3).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/corpus/global", CorpusViewResponse)

    async def reindex_corpus(self, request: ReindexRequest) -> ReindexResult:
        """Re-embed one scope under the configured embedding model (US-4.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/corpus/reindex", ReindexResult, request)

    async def purge_corpus(self, request: PurgeRequest) -> PurgeResponse:
        """Run the retention purge now, or purge one confirmed case (US-4.5).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/corpus/purge", PurgeResponse, request)

    async def corpus_audit(self, profile: str, case_id: str | None = None) -> AuditResponse:
        """Return a profile's audit entries, one case's when ``case_id`` is given (US-4.6).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        params = {"profile": profile} | ({} if case_id is None else {"case_id": case_id})
        return await self._request("GET", "/corpus/audit", AuditResponse, params=params)

    async def create_case(self, profile: str) -> Case:
        """Create an open, empty case in ``profile`` (US-5.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request(
            "POST", "/cases", Case, params={"profile": profile}, timeout=CASE_TIMEOUT
        )

    async def get_case(self, profile: str, case_id: str) -> Case:
        """Return a case with its source documents (US-5.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request(
            "GET", f"/cases/{case_id}", Case, params={"profile": profile}, timeout=CASE_TIMEOUT
        )

    async def upload_document(
        self, profile: str, case_id: str, body: bytes, content_type: str
    ) -> DocumentAdded:
        """Forward an upload's raw ``multipart/form-data`` body to the worker (US-5.1).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing is stored then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/documents",
            DocumentAdded,
            RawBody(body, content_type),
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def paste_text(self, profile: str, case_id: str, body: PastedText) -> DocumentAdded:
        """Attach pasted text to a case (US-5.1).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing is stored then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/paste",
            DocumentAdded,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def start_extraction(self, profile: str, case_id: str) -> JobStarted:
        """Start extracting a case; progress comes from ``job_events`` (US-5.2).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/extract",
            JobStarted,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def start_diagnosis(self, profile: str, case_id: str) -> JobStarted:
        """Start diagnosing an extracted case; progress comes from ``job_events`` (US-6.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/diagnose",
            JobStarted,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def start_draft(self, profile: str, case_id: str, body: DraftRequest) -> JobStarted:
        """Start drafting a diagnosed case's appeal; progress comes from ``job_events`` (US-7.1).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/draft",
            JobStarted,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def edit_draft(self, profile: str, case_id: str, body: DraftEdit) -> Case:
        """Store the biller's text as the case's draft (US-7.2).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing changes then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/draft/text",
            Case,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def export_draft(self, profile: str, case_id: str, body: ExportRequest) -> ExportedFile:
        """Write the case's draft as a PDF or DOCX file on this Mac (US-7.2).

        Raises:
            WorkerError: The call failed; the subclass names why. No file is written then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/export",
            ExportedFile,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def record_outcome(self, profile: str, case_id: str, body: OutcomeRequest) -> Case:
        """Store how the case ended, which closes it (US-8.1).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing changes then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/outcome",
            Case,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def weekly_summary(self, week: str | None) -> WeeklySummary:
        """Return the manager's summary of ``week``, the last completed week by default (US-8.2).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        params = {} if week is None else {"week": week}
        return await self._request(
            "GET", "/outcomes/summary", WeeklySummary, params=params, timeout=CASE_TIMEOUT
        )

    async def export_fine_tune(self, body: FineTuneExportRequest) -> FineTuneExport:
        """Write the manager-approved, de-identified fine-tune export (US-8.3).

        Raises:
            WorkerError: The call failed; the subclass names why. No file is written then.
        """
        return await self._request(
            "POST", "/outcomes/export", FineTuneExport, body, timeout=CASE_TIMEOUT
        )

    async def explain_code(self, body: ExplainCodeParams) -> ExplainCodeResult:
        """Return the global corpus entries for a code (US-9.1).

        Raises:
            WorkerError: The call failed; the subclass names why (``code_not_found``).
        """
        return await self._request(
            "POST", "/agent/explain-code", ExplainCodeResult, body, timeout=CASE_TIMEOUT
        )

    async def payer_rules(self, body: PayerRulesParams) -> PayerRulesResult:
        """Return the global rule cards of the payer ``body`` names (US-9.1).

        Raises:
            WorkerError: The call failed; the subclass names why (``payer_not_found``).
        """
        return await self._request(
            "POST", "/agent/rule-cards", PayerRulesResult, body, timeout=CASE_TIMEOUT
        )

    async def case_summary(self, profile: str, body: CaseSummaryParams) -> CaseSummaryResult:
        """Return ``profile``'s case reduced to codes, names, and enums (US-9.2; audited).

        Raises:
            WorkerError: The call failed; the subclass names why (``case_not_found``).
        """
        return await self._request(
            "POST",
            "/agent/case-summary",
            CaseSummaryResult,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def job_events(self, job_id: str, after: int, wait: float) -> JobEvents:
        """Return a job's events after position ``after``, waiting up to ``wait`` (US-5.2).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        params = {"after": str(after), "wait": str(wait)}
        return await self._request(
            "GET", f"/jobs/{job_id}/events", JobEvents, params=params, timeout=POLL_TIMEOUT
        )

    async def confirm_field(self, profile: str, case_id: str, body: FieldConfirmation) -> Case:
        """Store the biller's value for one field as confirmed (US-5.2).

        Raises:
            WorkerError: The call failed; the subclass names why. Nothing changes then.
        """
        return await self._request(
            "POST",
            f"/cases/{case_id}/fields",
            Case,
            body,
            params={"profile": profile},
            timeout=CASE_TIMEOUT,
        )

    async def _request(  # noqa: PLR0913 - the one funnel: method, path, model, body, query, timeout
        self,
        method: Literal["GET", "POST"],
        path: str,
        model: type[ModelT],
        body: BaseModel | RawBody | None = None,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ModelT:
        token = self._token_provider()
        if token is None:
            raise WorkerUnavailableError
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=timeout or self._timeout,
                trust_env=False,  # never route the token or case data through a proxy
            ) as client:
                headers = {"Authorization": f"Bearer {token}"}
                content: str | bytes | None = None
                if isinstance(body, RawBody):
                    content, headers["Content-Type"] = body.content, body.content_type
                elif body is not None:
                    headers["Content-Type"] = "application/json"
                    content = body.model_dump_json()
                response = await client.request(
                    method, path, headers=headers, content=content, params=params
                )
        except httpx.HTTPError as exc:
            raise WorkerUnavailableError from exc
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise WorkerUnauthorizedError
        if response.is_error:
            raise _rejection(response)
        try:
            return model.model_validate_json(response.content)
        except ValidationError as exc:
            raise InvalidWorkerResponseError from exc


def _rejection(response: httpx.Response) -> WorkerError:
    """Relay a worker error whose envelope carries a code the desktop half acts on.

    The status must be the one that code is answered with, so an unexpected failure that happens
    to carry such a code still maps to ``worker_error``.
    """
    try:
        code = ErrorEnvelope.model_validate_json(response.content).error.code
    except ValidationError:
        return WorkerFailedError()
    if RELAYED_CODES.get(code) == response.status_code:
        return WorkerRejectedError(code)
    return WorkerFailedError()
