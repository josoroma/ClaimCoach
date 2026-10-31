"""Read an X12 835 (ERA) into a ``Reading``: exact, so no model is involved.

Implements: US-5.2 (835 text pasted or uploaded fills the structured case), US-6.3 (the denial date
the appeal clock counts from). Rules: BR-1 (no model
and no network: plain parsing), BR-14 (nothing here logs content).

The ISA segment is fixed-width, so its 4th, 105th, and 106th characters give the element
separator, the component separator, and the segment terminator. A case is one claim: the first
``CLP`` loop is read and later claims are only counted. Segments read:

* the denial date (US-6.3), from the header of the transaction (``ST``) that holds the first claim:
  ``DTM*405`` (production date), else ``GS04`` of the enclosing group (the production date when
  ``DTM*405`` is absent), else ``BPR16`` (payment or EFT date, usually a few days later); only a
  valid ``CCYYMMDD`` counts;
* ``N1*PR`` payer name;
* ``CLP`` claim number (CLP07, the payer's control number, else CLP01), charge, payment;
* ``CAS`` adjustments (group code, then reason/amount/quantity triplets), on the claim until the
  first ``SVC`` and on the current line after it;
* ``MOA`` claim remark codes (MOA03 to MOA07);
* ``SVC`` service line (procedure code from the SVC01 composite, charge, payment);
* ``DTM*472`` (or ``DTM*150`` when 472 is absent) service date, ``LQ*HE`` line remark codes.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from claimcoach.cases.intake import is_edi_835
from claimcoach.pipeline.reading import Reading

__all__ = ["parse_835"]

_ISA_LENGTH: Final = 106
_MOA_REMARKS: Final = range(3, 8)


def _segments(text: str) -> tuple[list[list[str]], str]:
    interchange = text.lstrip("﻿ \t\r\n")
    element, component, terminator = (
        interchange[3],
        interchange[_ISA_LENGTH - 2],
        interchange[_ISA_LENGTH - 1],
    )
    segments = [part.strip() for part in interchange.split(terminator)]
    return [segment.split(element) for segment in segments if segment], component


def _get(segment: list[str], index: int) -> str | None:
    if index >= len(segment):
        return None
    return segment[index].strip() or None


def _date(value: str | None) -> str | None:
    """``CCYYMMDD`` → ISO; anything else is passed on as is and fails validation later."""
    if value is not None and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _valid_date(value: str | None) -> str | None:
    """``CCYYMMDD`` → ISO when it is a real date, else ``None`` (so the next source is tried)."""
    iso = _date(value)
    try:
        return date.fromisoformat(iso).isoformat() if iso and len(iso) == 10 else None
    except ValueError:
        return None


def _adjustments(segment: list[str]) -> list[dict[str, str | None]]:
    group = _get(segment, 1)
    return [
        {"group_code": group, "carc": _get(segment, index), "amount": _get(segment, index + 1)}
        for index in range(2, len(segment), 3)
        if _get(segment, index) is not None
    ]


def _line(segment: list[str], component: str) -> dict[str, Any]:
    composite = (_get(segment, 1) or "").split(component)
    code = composite[1] if len(composite) > 1 else composite[0]
    return {
        "procedure_code": code.strip() or None,
        "billed_amount": _get(segment, 2),
        "paid_amount": _get(segment, 3),
        "service_date": None,
        "dated_by": None,
        "adjustments": [],
        "rarc_codes": [],
    }


def _claim_segment(tag: str, segment: list[str], claim: dict[str, Any], component: str) -> None:
    """Apply one segment of the first claim's loop to ``claim``."""
    line: dict[str, Any] | None = claim["lines"][-1] if claim["lines"] else None
    if tag == "SVC":
        claim["lines"].append(_line(segment, component))
    elif tag == "CAS":
        (line or claim)["adjustments"] += _adjustments(segment)
    elif tag == "MOA":
        claim["rarc_codes"] += [code for i in _MOA_REMARKS if (code := _get(segment, i))]
    elif line is not None and tag == "DTM" and _get(segment, 1) in {"472", "150"}:
        if line["dated_by"] != "472":  # 472 (service date) wins over 150 (period start)
            line["service_date"], line["dated_by"] = _date(_get(segment, 2)), _get(segment, 1)
    elif line is not None and tag == "LQ" and _get(segment, 1) == "HE":
        line["rarc_codes"].append(_get(segment, 2))


def parse_835(text: str) -> tuple[Reading, int]:
    """Read the first claim of an 835 interchange.

    Args:
        text: The interchange (``cases.intake.is_edi_835`` holds for it).

    Returns:
        The claim as read, and how many more claims the interchange holds.

    Raises:
        ValueError: ``text`` is not an 835 interchange.
    """
    if not is_edi_835(text):
        raise ValueError("not an 835 interchange")
    segments, component = _segments(text)
    claim: dict[str, Any] = {"adjustments": [], "rarc_codes": [], "lines": []}
    claims = 0
    first = False  # inside the first claim's loop
    group_date: str | None = None  # GS04 of the current functional group
    header: dict[str, str | None] = {}  # this transaction's dates, until its first claim
    for segment in segments:
        tag = segment[0].strip()
        if tag == "GS":
            group_date = _valid_date(_get(segment, 4))
        elif tag == "ST":
            header = {}
        elif tag == "BPR" and claims == 0:
            header["paid"] = _valid_date(_get(segment, 16))
        elif tag == "DTM" and claims == 0 and _get(segment, 1) == "405":
            header["produced"] = _valid_date(_get(segment, 2))
        elif tag == "N1" and _get(segment, 1) == "PR":
            claim.setdefault("payer_name", _get(segment, 2))
        elif tag == "CLP":
            claims += 1
            first = claims == 1
            if first:
                claim["claim_id"] = _get(segment, 7) or _get(segment, 1)
                claim["billed_amount"] = _get(segment, 3)
                claim["paid_amount"] = _get(segment, 4)
                # The first claim's own transaction dates it; later transactions never do.
                claim["denial_date"] = header.get("produced") or group_date or header.get("paid")
        elif tag == "SE":
            first = False
        elif first:
            _claim_segment(tag, segment, claim, component)
    return Reading.model_validate(claim), max(claims - 1, 0)
