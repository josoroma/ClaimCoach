"""What one document (or page) says, before validation, and how readings become a case.

Implements: US-5.2 (``Reading``: the loose shape the 835 reader and the extraction model both
produce; ``build_extraction``: every value validated on its own into ``CaseExtraction``). Rules:
ES-1, BR-10 (a model reply is data: it is parsed as JSON into this shape and nothing else).

Merging: claim-level values come from the first source that reads them; claim lines, adjustments,
and remark codes all come from the first source that has any of them (835 text before other
documents, then in attach order), with that source's pages concatenated. Two documents describing
the same claim (an 835 and its EOB) therefore never duplicate lines.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, ValidationError

from claimcoach.cases.extraction import CaseExtraction, read_value

__all__ = [
    "AdjustmentReading",
    "LineReading",
    "Raw",
    "Reading",
    "SourceReading",
    "build_extraction",
]


def _scalar(value: object) -> object:
    """Text or a number; anything else (``true``, an object, a list) reads as absent."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    return value


Raw = Annotated[str | int | float | None, BeforeValidator(_scalar)]
"""A value as read: text or a number, or ``None`` when absent or of another JSON type."""


def _items(adapter: TypeAdapter[Any]) -> Callable[[object], list[Any]]:
    """Read a list one item at a time: ``null`` or a non-list is empty, a bad item is dropped."""

    def read(value: object) -> list[Any]:
        if not isinstance(value, list):
            return []
        items = []
        for item in value:
            try:
                items.append(adapter.validate_python(item))
            except ValidationError:
                continue  # one malformed item never loses the rest of the page
        return items

    return read


class _Loose(BaseModel):
    # A model reply may add keys; only these are read. Values stay raw until ``read_value``.
    model_config = ConfigDict(extra="ignore", frozen=True)


class AdjustmentReading(_Loose):
    """An adjustment as read."""

    group_code: Raw = None
    carc: Raw = None
    amount: Raw = None


Adjustments = Annotated[
    list[AdjustmentReading], BeforeValidator(_items(TypeAdapter(AdjustmentReading)))
]
Codes = Annotated[list[Raw], BeforeValidator(_items(TypeAdapter(Raw)))]


class LineReading(_Loose):
    """A service line as read."""

    procedure_code: Raw = None
    service_date: Raw = None
    billed_amount: Raw = None
    paid_amount: Raw = None
    adjustments: Adjustments = Field(default_factory=list)
    rarc_codes: Codes = Field(default_factory=list)


class Reading(_Loose):
    """One page's or one document's claim data as read.

    Every field tolerates what a model may answer: ``null`` lists, a malformed line among good
    ones, a boolean or an object where a value belongs. What cannot be read is absent, and
    ``build_extraction`` then marks it ``unreadable``.
    """

    payer_name: Raw = None
    claim_id: Raw = None
    billed_amount: Raw = None
    paid_amount: Raw = None
    adjustments: Adjustments = Field(default_factory=list)
    rarc_codes: Codes = Field(default_factory=list)
    lines: Annotated[list[LineReading], BeforeValidator(_items(TypeAdapter(LineReading)))] = Field(
        default_factory=list
    )


class SourceReading(BaseModel):
    """Everything read from one source document.

    Attributes:
        doc_id: The source document.
        readings: One per page (one for an image, an 835, or a text document); none when the
            document could not be decoded.
        other_claims: Claims an 835 held beyond the one read.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str
    readings: list[Reading]
    other_claims: int = 0


_SCALARS = ("payer_name", "claim_id", "billed_amount", "paid_amount")


def _adjustment(reading: AdjustmentReading) -> dict[str, object]:
    return {
        name: read_value(name, getattr(reading, name)) for name in ("group_code", "carc", "amount")
    }


def _codes(codes: list[Raw]) -> list[dict[str, object]]:
    return [read_value("rarc_codes", code) for code in codes]


def _line(reading: LineReading) -> dict[str, object]:
    return {
        "procedure_code": read_value("procedure_code", reading.procedure_code),
        "service_date": read_value("service_date", reading.service_date),
        "billed_amount": read_value("billed_amount", reading.billed_amount),
        "paid_amount": read_value("paid_amount", reading.paid_amount),
        "adjustments": [_adjustment(a) for a in reading.adjustments],
        "rarc_codes": _codes(reading.rarc_codes),
    }


def _first_readable(name: str, readings: Sequence[Reading]) -> dict[str, object]:
    unreadable = read_value(name, None)
    for reading in readings:
        value = read_value(name, getattr(reading, name))
        if value != unreadable:
            return value
    return unreadable


def _itemized(reading: Reading) -> bool:
    return bool(reading.lines or reading.adjustments or reading.rarc_codes)


def build_extraction(sources: Sequence[SourceReading]) -> CaseExtraction:
    """Validate and merge what every source said into one ``CaseExtraction``.

    Args:
        sources: Per-source readings, in priority order (835 text first).

    Returns:
        The extraction; any value that is missing or invalid everywhere is ``unreadable``.
    """
    every = [reading for source in sources for reading in source.readings]
    data: dict[str, Any] = {name: _first_readable(name, every) for name in _SCALARS}
    itemized = next((s for s in sources if any(_itemized(r) for r in s.readings)), None)
    body = itemized.readings if itemized else []
    data["adjustments"] = [_adjustment(a) for r in body for a in r.adjustments]
    data["rarc_codes"] = _codes([code for r in body for code in r.rarc_codes])
    data["lines"] = [_line(line) for r in body for line in r.lines]
    data["other_claims"] = sum(source.other_claims for source in sources)
    data["sources"] = [source.doc_id for source in sources]
    data["itemized_by"] = itemized.doc_id if itemized else None
    data["unread_sources"] = [source.doc_id for source in sources if not source.readings]
    return CaseExtraction.model_validate(data)
