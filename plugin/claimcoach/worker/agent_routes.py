"""Worker routes behind the Hermes agent tools.

Implements: US-9.1 (``POST /agent/explain-code``, ``POST /agent/rule-cards``: global reference
material), US-9.2 (``POST /agent/case-summary``: one profile's case reduced to codes, names, and
enums, audited ``case_summarized``). Rules: ES-8 (the tool's own parameter model is the body; a
``CorpusError`` becomes its fixed envelope in ``create_app``), BR-3, BR-4 (nothing here sends or
transmits; ``test_us_7_3_no_transmitting_route`` pins the route set), BR-14, PC-4.

The tool arguments travel in the body, never in the URL. Routes are plain ``def``: FastAPI runs
them in its thread pool, so opening a user store (a Keychain prompt) never stalls the event loop.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from claimcoach.agent.answers import case_summary, explain_code, payer_rules
from claimcoach.agent.types import (
    CaseSummaryParams,
    CaseSummaryResult,
    ExplainCodeParams,
    ExplainCodeResult,
    PayerRulesParams,
    PayerRulesResult,
)
from claimcoach.cases.service import CaseService
from claimcoach.corpus.types import DEFAULT_PROFILE, ProfileName
from claimcoach.worker.case_routes import get_cases
from claimcoach.worker.corpus_routes import Corpus

__all__ = ["router"]

router = APIRouter(prefix="/agent")


@router.post("/explain-code", response_model=ExplainCodeResult)
def explain(body: ExplainCodeParams, corpus: Corpus) -> ExplainCodeResult:
    """Answer ``claimcoach_explain_code`` from the global code entries."""
    return explain_code(corpus.global_store(), body.code, date.today())


@router.post("/rule-cards", response_model=PayerRulesResult)
def rules(body: PayerRulesParams, corpus: Corpus) -> PayerRulesResult:
    """Answer ``claimcoach_payer_rules`` from the global rule cards."""
    return payer_rules(corpus.global_store(), body.payer, date.today())


@router.post("/case-summary", response_model=CaseSummaryResult)
def summary(
    body: CaseSummaryParams,
    cases: Annotated[CaseService, Depends(get_cases)],
    profile: Annotated[ProfileName, Query()] = DEFAULT_PROFILE,
) -> CaseSummaryResult:
    """Answer ``claimcoach_case_summary`` for ``profile``'s case."""
    return case_summary(cases, profile, body.case_id)
