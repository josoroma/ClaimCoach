"""Worker routes over case outcomes beyond one case: the manager's summary and export.

Implements: US-8.2 (``GET /outcomes/summary``: one ISO week of opted-in profiles' de-identified
outcomes), US-8.3 (``POST /outcomes/export``: the manager-approved fine-tune export, refused with
``export_not_approved`` before anything is read). Rules: ES-8 (typed bodies; a bad ``week`` is the
``invalid_request`` envelope), BR-14 (the summary carries counts, enums, codes, rule-card payer
names, and profile names only), PRD §9 (it reads the outcomes table only, never a case document).

Routes are plain ``def``: FastAPI runs them in its thread pool, so reading every profile's
database never stalls the event loop.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from claimcoach.outcomes.export import export_fine_tune
from claimcoach.outcomes.summary import build_weekly_summary
from claimcoach.outcomes.types import (
    FineTuneExport,
    FineTuneExportRequest,
    IsoWeek,
    WeeklySummary,
)
from claimcoach.worker.corpus_routes import Corpus

__all__ = ["router"]

router = APIRouter(prefix="/outcomes")


@router.get("/summary", response_model=WeeklySummary)
def weekly_summary(
    corpus: Corpus, week: Annotated[IsoWeek | None, Query()] = None
) -> WeeklySummary:
    """Summarize ``week`` (the last completed week by default) in this Mac's time zone."""
    return build_weekly_summary(corpus.root, week)


@router.post("/export", response_model=FineTuneExport)
def fine_tune_export(corpus: Corpus, body: FineTuneExportRequest) -> FineTuneExport:
    """Write the de-identified fine-tune export once the manager approved it (US-8.3)."""
    return export_fine_tune(corpus.root, body)
