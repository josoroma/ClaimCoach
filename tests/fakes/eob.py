"""A synthetic, PHI-free EOB for extraction tests: a PDF and what a good model reads from it.

Implements: US-5.2 test harness (ES-4: offline; the fake OpenAI-compatible server answers with
``eob_reply()`` as Qwen3-VL-8B would). The real-model test reads the same PDF with the real model.
"""

from __future__ import annotations

import json
from typing import Any, Final

import pymupdf

__all__ = ["EOB_LINES", "EOB_READING", "eob_reply", "synthetic_eob_pdf"]

EOB_LINES: Final = (
    "ACME HEALTH PLAN - EXPLANATION OF BENEFITS",
    "Claim number: CLAIM-77        Provider: SYNTHETIC CLINIC",
    "Total billed: $250.00         Total paid: $0.00",
    "",
    "Line  Date of service  Procedure  Billed    Paid   Adjustment       Remarks",
    "1     2026-09-01       99213      $250.00   $0.00  CO-197 $250.00   N286",
    "",
    "CO-197: Precertification/authorization/notification absent.",
    "N286: Missing/incomplete/invalid referring provider primary identifier.",
)
"""The page's text: one denied line, CO-197 with remark N286. No person is named."""

EOB_READING: Final[dict[str, Any]] = {
    "payer_name": "ACME HEALTH PLAN",
    "claim_id": "CLAIM-77",
    "billed_amount": "250.00",
    "paid_amount": "0.00",
    "adjustments": [],
    "rarc_codes": [],
    "lines": [
        {
            "procedure_code": "99213",
            "service_date": "2026-09-01",
            "billed_amount": "$250.00",
            "paid_amount": 0,
            "adjustments": [{"group_code": "CO", "carc": "197", "amount": "250.00"}],
            "rarc_codes": ["N286"],
        }
    ],
}


def eob_reply(**changes: Any) -> str:
    """The JSON a good model answers for the EOB page, with top-level ``changes`` applied."""
    return json.dumps(EOB_READING | changes)


def synthetic_eob_pdf(pages: int = 1) -> bytes:
    """Return a letter-size PDF whose every page holds ``EOB_LINES``."""
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    for _ in range(pages):
        page = document.new_page(width=612, height=792)
        for index, line in enumerate(EOB_LINES):
            page.insert_text((36, 60 + 18 * index), line, fontsize=9, fontname="cour")
    data = bytes(document.tobytes())  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return data
