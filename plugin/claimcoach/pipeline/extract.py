"""Structured extraction: every source document of a case read into one ``CaseExtraction``.

Implements: US-5.2 (PyMuPDF renders PDF pages; Qwen3-VL-8B, the ``extraction`` role, reads each
page or image through the registered ``extraction`` template; 835 text goes to ``parse_835``; each
value is validated on its own and what fails is ``unreadable``; progress is reported per page).
Rules: BR-1 and BR-2 (the model is held through ``ModelManager.use`` on loopback), BR-10 (document
text and page images are data blocks of a ``BuiltPrompt``; the reply is parsed as JSON into
``Reading`` and nothing else), BR-14 (logs carry error types only).

Runs in the worker only: it imports PyMuPDF, which the gateway does not have.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

import httpx
import pymupdf
from pydantic import ValidationError

from claimcoach.cases.extraction import CaseExtraction
from claimcoach.cases.models import SourceDocument
from claimcoach.cases.service import CaseService
from claimcoach.events import CaseStage
from claimcoach.logs import get_logger
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import EndpointProvider, ModelEndpoint
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.edi835 import parse_835
from claimcoach.pipeline.reading import Reading, SourceReading, build_extraction
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template

__all__ = [
    "EXTRACTION_TEMPLATE",
    "MAX_PDF_PAGES",
    "Extractor",
    "Report",
    "Unit",
    "parse_reply",
    "rasterize_pdf",
    "to_png",
]

MAX_PDF_PAGES: Final = 30
"""Pages read per PDF; an EOB for one claim is a few pages."""
RENDER_DPI: Final = 150
MAX_SIDE: Final = 2000
"""Longest side in pixels of a page image: enough for small print, bounded for odd page sizes."""
TEXT_CHUNK: Final = 12_000
"""Characters of a text document per model call."""
MAX_TOKENS: Final = 2048
PAGE_TIMEOUT: Final = 600.0
"""Seconds per page: an 8B vision model on an M3 Pro takes well under a minute."""
EXTRACTING_SHARE: Final = 0.95
"""Progress reached when the last page is read; storing the result completes it."""

Report = Callable[[CaseStage, float], None]
"""Called with each stage and the fraction of the job done."""

EXTRACTION_TEMPLATE: Final = define_template(
    "extraction",
    system=(
        "You read pages of US health-insurance remittance documents (EOBs, ERAs, and payer "
        "denial letters) and copy the claim data printed on them into JSON. Copy values exactly "
        "as printed. Never guess: use null for anything you cannot read."
    ),
    instructions=(
        "Return one JSON object and nothing else, with these keys: payer_name; claim_id (the "
        "payer's claim number); billed_amount; paid_amount; adjustments (claim-level, a list of "
        "objects with group_code, carc, amount); rarc_codes (claim-level remark codes); lines (a "
        "list of objects with procedure_code, service_date as YYYY-MM-DD, billed_amount, "
        "paid_amount, adjustments, rarc_codes). Amounts are plain numbers without currency "
        "symbols. group_code is CO, PR, OA, PI, or CR and carc is the reason code that follows "
        "it (CO-197 is group_code CO, carc 197). Remark codes look like N286, M15, or MA130. Use "
        "null or an empty list for anything not on this page. The page image, when attached, is "
        "part of the data."
    ),
)

_log = get_logger("claimcoach.pipeline")
_THINK: Final = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Unit:
    """One model call's worth of a document: a page image, its text, or both.

    Attributes:
        label: Where it is (``page 2 of 3``); a data item, never an instruction.
        image: PNG bytes, if any.
        text: Text (a PDF page's text layer, or a slice of a text document), if any.
    """

    label: str
    image: bytes | None = None
    text: str | None = None


def rasterize_pdf(data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> list[Unit]:
    """Render each page as PNG at 150 dpi (less for a page over ``MAX_SIDE`` px), with its text.

    The only function that renders PDFs, so another renderer can replace PyMuPDF here alone.

    Raises:
        RuntimeError: The PDF cannot be opened (PyMuPDF's ``FileDataError``).
    """
    # PyMuPDF ships py.typed but leaves some constructors unannotated.
    with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        count = min(document.page_count, max_pages)
        return [
            Unit(
                label=f"page {index + 1} of {count}",
                image=page.get_pixmap(dpi=_dpi(page.rect.width, page.rect.height)).tobytes("png"),
                text=page.get_text().strip() or None,
            )
            for index, page in enumerate(document.pages(0, count))
        ]


def _dpi(width_pt: float, height_pt: float) -> int:
    """The render resolution that keeps a page's longest side at most ``MAX_SIDE`` pixels."""
    longest = max(width_pt, height_pt, 1.0) / 72  # inches
    return max(1, min(RENDER_DPI, int(MAX_SIDE / longest)))


def to_png(data: bytes) -> bytes:
    """Re-encode a PNG or JPEG as PNG, in RGB or grey, at most ``MAX_SIDE`` px on its longest side.

    A CMYK scan is converted to RGB (PNG has no CMYK). Decoding also proves the image is whole.
    """
    pixmap = pymupdf.Pixmap(data)  # type: ignore[no-untyped-call]
    if pixmap.colorspace is not None and pixmap.colorspace.n == 4:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)  # type: ignore[no-untyped-call]
    while max(pixmap.width, pixmap.height) > MAX_SIDE:
        pixmap.shrink(1)  # type: ignore[no-untyped-call] # halves both sides
    return bytes(pixmap.tobytes("png"))  # type: ignore[no-untyped-call]


def _text_units(text: str) -> list[Unit]:
    parts = [text[start : start + TEXT_CHUNK] for start in range(0, len(text), TEXT_CHUNK)]
    return [
        Unit(label=f"part {index + 1} of {len(parts)}", text=part)
        for index, part in enumerate(parts)
    ]


def units_of(document: SourceDocument, data: bytes) -> list[Unit]:
    """Split a non-835 source document into model calls.

    Raises:
        Exception: PyMuPDF's error types when the PDF or image does not decode.
    """
    if document.kind == "pdf":
        return rasterize_pdf(data)
    if document.kind == "image":
        return [Unit(label="page 1 of 1", image=to_png(data))]
    return _text_units(data.decode("utf-8"))


def parse_reply(content: str) -> Reading | None:
    """Return the reply's JSON object as a ``Reading``, or ``None`` when there is none.

    Tolerates a ``<think>`` block and code fences around the object; nothing else is read.
    """
    text = _THINK.sub("", content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return Reading.model_validate(json.loads(text[start : end + 1]))
    except (ValueError, ValidationError):
        return None


@dataclass
class _Plan:
    document: SourceDocument
    reading: SourceReading | None = None
    units: Sequence[Unit] = ()


class Extractor:
    """Reads a case's source documents into its ``CaseExtraction``.

    Args:
        cases: Where the sources and the extraction are stored.
        models: ``ModelManager.use`` (or a test double); used only when a page needs the model.
        transport: Optional httpx transport for the model calls (tests).
    """

    def __init__(
        self,
        cases: CaseService,
        models: EndpointProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Keep the collaborators; nothing runs until ``run``."""
        self.cases = cases
        self.models = models
        self._transport = transport

    async def run(self, profile: str, case_id: str, report: Report) -> CaseExtraction:
        """Extract the case, store the result, and report progress.

        Raises:
            ModelUnavailableError: The extraction model is missing or stopped answering.
            ModelBusyError: The memory guard kept the model queued too long.
            CorpusError: The case store failed (for example the case was closed meanwhile).
        """
        report("extracting", 0.0)
        sources = await asyncio.to_thread(self.cases.sources, profile, case_id)
        # 835 text first: it is exact, so its lines win over a scanned copy of the same claim.
        ordered = sorted(sources, key=lambda source: source[0].kind != "edi_835")
        plans = [await asyncio.to_thread(_plan, document, data) for document, data in ordered]
        pending = [plan for plan in plans if plan.reading is None]
        total = len(plans) - len(pending) + sum(len(plan.units) for plan in pending)
        done = len(plans) - len(pending)  # 835s and undecodable files are read already
        if done:
            report("extracting", EXTRACTING_SHARE * done / total)
        if pending:  # the model is loaded only when a page needs it
            async with self.models(ModelRole.EXTRACTION) as endpoint:
                for plan in pending:
                    pages = []
                    for unit in plan.units:
                        pages.append(await self._read(endpoint, unit))
                        done += 1
                        report("extracting", EXTRACTING_SHARE * done / total)
                    plan.reading = SourceReading(doc_id=plan.document.doc_id, readings=pages)
        extraction = build_extraction([plan.reading for plan in plans if plan.reading])
        await asyncio.to_thread(self.cases.save_extraction, profile, case_id, extraction)
        report("done", 1.0)
        return extraction

    async def _read(self, endpoint: ModelEndpoint, unit: Unit) -> Reading:
        data = [DataItem(label="page", text=unit.label)]
        if unit.text:
            data.append(DataItem(label="page_text", text=unit.text))
        prompt = build_prompt(PromptParts(template=EXTRACTION_TEMPLATE, data=tuple(data)))
        reply = await chat_completion(
            endpoint,
            prompt,
            max_tokens=MAX_TOKENS,
            images=() if unit.image is None else (unit.image,),
            timeout=PAGE_TIMEOUT,
            transport=self._transport,
        )
        return parse_reply(reply.content) or Reading()


def _plan(document: SourceDocument, data: bytes) -> _Plan:
    """Parse an 835 now, or split another document into model calls (CPU work: a thread)."""
    if document.kind == "edi_835":
        reading, others = parse_835(data.decode("utf-8"))
        return _Plan(
            document, SourceReading(doc_id=document.doc_id, readings=[reading], other_claims=others)
        )
    try:
        units = units_of(document, data)
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises unrelated types for corrupt files
        # The document is skipped: its fields stay unreadable and the biller confirms them.
        _log.warning("a source document could not be decoded: %s", type(exc).__name__)
        units = []
    if not units:
        return _Plan(document, SourceReading(doc_id=document.doc_id, readings=[]))
    return _Plan(document, units=units)
