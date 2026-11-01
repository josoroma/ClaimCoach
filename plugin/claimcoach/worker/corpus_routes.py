"""Worker routes over the corpus scopes.

Implements: US-4.1 (``GET /corpus/status``, ``POST /corpus/reindex``), US-4.3 (``POST
/corpus/import``, ``GET /corpus/global``), US-4.5 (``POST /corpus/purge``), US-4.6 (``GET
/corpus/audit``), US-10.3 (``GET /corpus/status?profile=`` reports only that profile's user
scope, so the settings page reads no other profile's key). Rules: ES-8 (typed bodies; a
``CorpusError`` becomes its fixed envelope in ``create_app``), BR-14 (responses carry IDs, counts,
dates, and global reference material only; never case content).

Routes that open stores or delete are plain ``def``: FastAPI runs them in its thread pool, so a
Keychain prompt or a long secure-delete never stalls the event loop.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from claimcoach.corpus.bundle import CorpusBundle, CorpusViewResponse, ImportResult
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import (
    DEFAULT_PROFILE,
    AuditResponse,
    CaseId,
    CorpusStatusResponse,
    ProfileName,
    PurgeRequest,
    PurgeResponse,
    ReindexRequest,
    ReindexResult,
)

__all__ = ["get_corpus", "router"]

router = APIRouter(prefix="/corpus")


def get_corpus(request: Request) -> CorpusService:
    """Return the worker's corpus service (set by ``create_app``)."""
    return cast("CorpusService", request.app.state.corpus)


Corpus = Annotated[CorpusService, Depends(get_corpus)]


@router.get("/status", response_model=CorpusStatusResponse)
def status(
    corpus: Corpus, profile: Annotated[ProfileName | None, Query()] = None
) -> CorpusStatusResponse:
    """Report both scopes: paths, counts, encryption, and the index's embedding model.

    With ``profile``, only that profile's user scope is reported (US-10.3).
    """
    return corpus.status(profile)


@router.post("/import", response_model=ImportResult)
async def import_bundle(body: CorpusBundle, corpus: Corpus) -> ImportResult:
    """Import a validated bundle into the global scope, all or nothing."""
    return await corpus.import_bundle(body)


@router.get("/global", response_model=CorpusViewResponse)
def global_view(corpus: Corpus) -> CorpusViewResponse:
    """List the global items with source, verified-on date, and stale flag."""
    return corpus.view()


@router.post("/reindex", response_model=ReindexResult)
async def reindex(body: ReindexRequest, corpus: Corpus) -> ReindexResult:
    """Re-embed one scope under the configured embedding model."""
    return await corpus.reindex(body)


@router.post("/purge", response_model=PurgeResponse)
def purge(body: PurgeRequest, corpus: Corpus) -> PurgeResponse:
    """Run the retention purge now, or purge one confirmed case."""
    return corpus.purge(body)


@router.get("/audit", response_model=AuditResponse)
def audit(
    corpus: Corpus,
    profile: Annotated[ProfileName, Query()] = DEFAULT_PROFILE,
    case_id: Annotated[CaseId | None, Query()] = None,
) -> AuditResponse:
    """Return a profile's audit entries, only one case's when ``case_id`` is given."""
    return corpus.audit(profile, case_id)
