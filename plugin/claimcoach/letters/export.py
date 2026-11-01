"""Export: the stored appeal draft as a PDF or DOCX file the biller saves.

Implements: US-7.2 (``render_pdf`` with PyMuPDF; ``render_docx``, the smallest valid
WordprocessingML package, written with ``zipfile``; ``Exports``, which writes each export to the
profile's owner-only ``exports`` folder and deletes it 15 minutes later, or when the worker stops),
US-7.1 (every export
carries the label "draft for human review": on each PDF page and as the DOCX's first paragraph),
US-7.4 (``correction_text`` and ``render_correction``: a corrected-claim draft as a numbered list
of changes, through the same writers, exported as ``corrected-claim-draft-<case>.<ext>``).
Rules: BR-4 (an export is a file on this Mac; nothing here sends, submits, or uploads it), BR-6
(an export is plaintext PHI outside the encrypted store, so it lives 15 minutes in a 0700 folder
as a 0600 file), BR-13, BR-14 (logs carry counts and error types only).

The draft rendered is the stored one, never text from a request (design decision 2).
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import secrets
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal
from xml.sax.saxutils import escape

import pymupdf

from claimcoach.corpus.paths import exports_dirs, profile_exports_dir
from claimcoach.corrections.types import (
    FIELD_LABELS,
    FREQUENCY_MEANINGS,
    NOT_IN_DOCUMENTS,
    ClaimCorrection,
    CorrectedClaimDraft,
)
from claimcoach.letters.types import AppealDraft, ExportedFile, ExportFormat
from claimcoach.logs import get_logger

__all__ = [
    "EXPORT_TTL",
    "SWEEP_INTERVAL",
    "ExportStem",
    "Exports",
    "correction_text",
    "render",
    "render_correction",
    "render_docx",
    "render_pdf",
]

EXPORT_TTL: Final = 15 * 60.0
"""Seconds an export stays on disk (design decision 4)."""
SWEEP_INTERVAL: Final = 60.0
"""Seconds between sweeps of expired exports."""
TITLE: Final = "Appeal letter (draft for human review)"
CORRECTION_TITLE: Final = "Corrected claim (draft for human review)"
HEADER: Final = "Draft for human review"
"""The label as the export's header and first line show it (BR-4)."""

ExportStem = Literal["appeal-draft", "corrected-claim-draft"]
"""What an export holds: the appeal letter (US-7.2) or the corrected-claim draft (US-7.4)."""

_NAME: Final = re.compile(
    r"^(?:appeal-draft|corrected-claim-draft)-[A-Za-z0-9_-]{1,64}-[0-9a-f]{16}\.(pdf|docx)$"
)
"""What an export's stored name looks like; the sweep touches nothing else."""
_XML_INVALID: Final = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")
"""Characters XML 1.0 cannot hold (control characters, unpaired surrogates); neither format gets
them: a NUL would end MuPDF's text, and the others render as stray glyphs."""
_CSS: Final = (
    "body { font-family: sans-serif; font-size: 11pt; line-height: 1.3; } "
    "p { margin: 0 0 4pt 0; white-space: pre-wrap; }"
)
_PAGE: Final = pymupdf.paper_rect("letter")
_MARGIN: Final = 72.0
"""One inch."""

_log = get_logger("claimcoach.letters")


def _is_export(name: str) -> bool:
    """An export, or the temporary file of one being written; the folder holds nothing else."""
    partial = name.startswith(".") and name.endswith(".partial")
    return bool(
        _NAME.fullmatch(name.removeprefix(".").removesuffix(".partial") if partial else name)
    )


def _lines(text: str) -> list[str]:
    """The text's lines, without characters either format cannot hold."""
    printable = _XML_INVALID.sub("", text)
    return printable.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def render_pdf(draft: AppealDraft) -> bytes:
    """Return the draft as a US Letter PDF: one paragraph per line, the label on every page."""
    return _pdf(draft.text, TITLE)


def _pdf(text: str, title: str) -> bytes:
    """``text`` as a US Letter PDF titled ``title``, one paragraph per line, labeled per page.

    Paragraphs are built through the Story DOM, never from HTML text, so the letter's own text
    (``AT&amp;T``, ``x &lt; y``) is laid out as written.
    """
    story = pymupdf.Story(user_css=_CSS)  # type: ignore[no-untyped-call]
    for line in _lines(text):
        story.body.add_paragraph().add_text(line or "\u00a0")  # an empty line keeps its height
    laid_out = io.BytesIO()
    writer = pymupdf.DocumentWriter(laid_out)  # type: ignore[no-untyped-call]
    where = pymupdf.Rect(_MARGIN, _MARGIN + 18, _PAGE.width - _MARGIN, _PAGE.height - _MARGIN)  # type: ignore[no-untyped-call]
    more = True
    while more:
        device = writer.begin_page(_PAGE)  # type: ignore[no-untyped-call]
        more, _filled = story.place(where)  # type: ignore[no-untyped-call]
        story.draw(device)  # type: ignore[no-untyped-call]
        writer.end_page()  # type: ignore[no-untyped-call]
    writer.close()  # type: ignore[no-untyped-call]
    with pymupdf.open(stream=laid_out.getvalue(), filetype="pdf") as document:  # type: ignore[no-untyped-call]
        for page in document:
            page.insert_text((_MARGIN, _MARGIN - 18), HEADER, fontname="helv", fontsize=9)
        document.set_metadata({"title": title, "creator": "ClaimCoach", "producer": "ClaimCoach"})
        data: bytes = document.tobytes(garbage=3, deflate=True)
    return data


def _xml(text: str) -> str:
    return escape(_XML_INVALID.sub("", text))


_W: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CONTENT_TYPES: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/docProps/core.xml" '
    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    "</Types>"
)
_RELS: Final = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Target="word/document.xml" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument"/>'
    '<Relationship Id="rId2" Target="docProps/core.xml" Type="http://schemas.openxmlformats.org/'
    'package/2006/relationships/metadata/core-properties"/>'
    "</Relationships>"
)


def _paragraph(text: str, *, bold: bool = False) -> str:
    style = "<w:rPr><w:b/></w:rPr>" if bold else ""
    run = f'<w:r>{style}<w:t xml:space="preserve">{_xml(text)}</w:t></w:r>' if text else ""
    return f"<w:p>{run}</w:p>"


def _core(created: datetime, title: str) -> str:
    stamp = created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{_xml(title)}</dc:title><dc:creator>ClaimCoach</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        "</cp:coreProperties>"
    )


def render_docx(draft: AppealDraft) -> bytes:
    """Return the draft as a DOCX: the label in bold, then one paragraph per line."""
    return _docx(draft.text, TITLE, draft.edited_at or draft.drafted_at)


def _docx(text: str, title: str, created: datetime) -> bytes:
    """``text`` as a DOCX titled ``title``: the label in bold, then one paragraph per line."""
    paragraphs = [_paragraph(HEADER, bold=True), *(_paragraph(line) for line in _lines(text))]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W}"><w:body>{"".join(paragraphs)}'
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        # [Content_Types].xml first: some readers expect it at the start of the archive.
        package.writestr("[Content_Types].xml", _CONTENT_TYPES)
        package.writestr("_rels/.rels", _RELS)
        package.writestr("word/document.xml", document)
        package.writestr("docProps/core.xml", _core(created, title))
    return buffer.getvalue()


def render(draft: AppealDraft, export_format: ExportFormat) -> bytes:
    """Return the draft rendered as ``export_format``."""
    renderers: dict[ExportFormat, Callable[[AppealDraft], bytes]] = {
        ExportFormat.PDF: render_pdf,
        ExportFormat.DOCX: render_docx,
    }
    return renderers[export_format](draft)


def _change_heading(number: int, change: ClaimCorrection) -> str:
    where = "Claim" if change.line is None else f"Line {change.line}"
    now = change.current_value or NOT_IN_DOCUMENTS
    return f"{number}. {where}, {FIELD_LABELS[change.field]} (current value: {now})"


def correction_text(correction: CorrectedClaimDraft, *, stale: bool = False) -> str:
    """The corrected-claim draft as text: what to do, then one numbered item per change.

    ``stale``: the case changed after it was drafted, which the text says first.
    """
    code = correction.frequency_code
    cards = ", ".join(correction.rule_cards) or "none on file for this payer"
    lines = [
        f"Corrected claim: {correction.label}",
        f"Original claim number: {correction.original_claim_id or NOT_IN_DOCUMENTS}",
        f"Claim frequency code: {code} ({FREQUENCY_MEANINGS[code]})",
        f"Payer rule cards on file when drafted: {cards}",
        "",
        "Make and check these changes in your billing system. ClaimCoach does not send, submit, "
        "or file claims; nothing here leaves this Mac.",
    ]
    if stale:
        lines[1:1] = [
            "OUT OF DATE: the case changed after this draft was made. Check it, or draft it again."
        ]
    for number, change in enumerate(correction.corrections, 1):
        codes = ", ".join(change.because) or "none read"
        lines += [
            "",
            _change_heading(number, change),
            f"What to check or change: {change.action}",
            f"Why: {change.why}",
            f"Codes: {codes}",
        ]
    if correction.omitted:
        lines += [
            "",
            f"{correction.omitted} more change(s) are not listed: the codes point at more lines "
            "than one draft lists. Check every line of the claim.",
        ]
    lines += ["", f"Drafted {correction.drafted_at.date().isoformat()} for human review."]
    return "\n".join(lines)


def render_correction(
    correction: CorrectedClaimDraft, export_format: ExportFormat, *, stale: bool = False
) -> bytes:
    """Return the corrected-claim draft rendered as ``export_format`` (US-7.4 design decision 9)."""
    text = correction_text(correction, stale=stale)
    if export_format is ExportFormat.PDF:
        return _pdf(text, CORRECTION_TITLE)
    return _docx(text, CORRECTION_TITLE, correction.drafted_at)


class Exports:
    """Exported drafts on this Mac, each removed ``EXPORT_TTL`` seconds after it is written.

    Args:
        root: The Hermes root whose profiles' ``exports`` folders are used.
        clock: Wall-clock seconds (tests inject one); compared with each file's modified time.
        interval: Seconds between sweeps in ``run``.
    """

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], float] = time.time,
        interval: float = SWEEP_INTERVAL,
    ) -> None:
        """Keep the root; nothing is written until ``write``."""
        self.root = root
        self._clock = clock
        self._interval = interval

    def write(
        self,
        profile: str,
        case_id: str,
        export_format: ExportFormat,
        data: bytes,
        *,
        stem: ExportStem = "appeal-draft",
    ) -> ExportedFile:
        """Write one export (0600, through a temporary name) after sweeping expired ones.

        ``stem`` names what it holds: the appeal draft, or the corrected-claim draft (US-7.4).

        Raises:
            InvalidProfileError: ``profile`` is not a Hermes profile name.
            OSError: The folder or file could not be written.
        """
        self.sweep()
        folder = profile_exports_dir(profile, self.root)
        suffix = export_format.value
        target = folder / f"{stem}-{case_id}-{secrets.token_hex(8)}.{suffix}"
        partial = target.with_name(f".{target.name}.partial")
        now = self._clock()
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.utime(partial, (now, now))
            partial.replace(target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return ExportedFile(
            case_id=case_id,
            format=export_format,
            path=str(target),
            filename=f"{stem}-{case_id}.{suffix}",
            size_bytes=len(data),
            expires_at=datetime.fromtimestamp(now + EXPORT_TTL, UTC),
        )

    def sweep(self) -> int:
        """Delete every export written more than ``EXPORT_TTL`` seconds ago; return how many."""
        cutoff = self._clock() - EXPORT_TTL
        removed = 0
        for folder in exports_dirs(self.root):
            for path in folder.iterdir():
                if not _is_export(path.name):
                    continue
                try:
                    if path.lstat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except FileNotFoundError:  # removed by a concurrent sweep
                    continue
        return removed

    def clear(self) -> int:
        """Delete every export, expired or not; return how many (the worker's shutdown)."""
        removed = 0
        for folder in exports_dirs(self.root):
            for path in folder.iterdir():
                if _is_export(path.name):
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed

    async def shutdown(self) -> None:
        """Delete every export: once the worker stops, no save dialog can still need one."""
        removed = await asyncio.to_thread(self.clear)
        if removed:
            _log.info("worker shutdown removed %d exports", removed)

    async def run(self) -> None:
        """Sweep now, then every ``interval`` seconds, until cancelled."""
        while True:
            try:
                removed = await asyncio.to_thread(self.sweep)
            except OSError as exc:  # the schedule must outlive one bad run
                _log.error("export sweep failed: %s", type(exc).__name__)
            else:
                if removed:
                    _log.info("export sweep removed %d expired exports", removed)
            await asyncio.sleep(self._interval)
