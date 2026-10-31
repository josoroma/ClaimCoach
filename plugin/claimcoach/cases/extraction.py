"""The structured case: typed claim fields, each extracted, unreadable, or confirmed.

Implements: US-5.2 (``FieldStatus``, ``Extracted``, ``Adjustment``, ``ClaimLine``,
``CaseExtraction`` with field paths, the fields that need confirmation, confirmation, and keeping
confirmations across a re-run; ``FieldConfirmation``; ``JobStarted``; ``JobEvents``), US-6.1
(``CaseExtraction.digest``, so a diagnosis knows what it read; ``JobKind``), US-6.3
(``CaseExtraction.denial_date``, the date the appeal clock counts from; ``IsoDate``: dates are
read only as ``YYYY-MM-DD``), US-7.1 (the ``draft`` job kind). Rules: ES-1
(Pydantic v2, ``extra="forbid"``, frozen), BR-14 (these models hold case content: they travel
worker → gateway → pane only and are never logged or put in an event).

Every value has its own validator (``READERS``), so a reading is validated one value at a time
(``read_value``): what does not validate is ``unreadable`` instead of failing the whole case.
This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Final, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from claimcoach.events import CaseProgressEvent

__all__ = [
    "FIELD_PATH_PATTERN",
    "JOB_DEADLINE",
    "READERS",
    "Adjustment",
    "CarcCode",
    "CaseExtraction",
    "ClaimLine",
    "ClaimNumber",
    "Extracted",
    "FieldConfirmation",
    "FieldStatus",
    "GroupCode",
    "IsoDate",
    "JobEvents",
    "JobKind",
    "JobStarted",
    "Money",
    "PayerName",
    "ProcedureCode",
    "RarcCode",
    "read_value",
]

JOB_DEADLINE: Final = 3600.0
"""Seconds one extraction job may run; past it the job stops and ends ``processing_timeout``."""

_ITEMIZED: Final = frozenset({"adjustments", "rarc_codes", "lines"})
FIELD_PATH_PATTERN: Final = r"^[a-z_]{1,32}(?:\.\d{1,3}(?:\.[a-z_]{1,32})?)*$"
"""``payer_name``, ``lines.0.service_date``, ``lines.0.adjustments.1.carc``, ``rarc_codes.2``."""


def _code(value: object) -> object:
    """Codes compare upper-case and without surrounding spaces (``co`` → ``CO``)."""
    return value.strip().upper() if isinstance(value, str) else value


def _amount(value: object) -> object:
    """Money as printed: ``$1,250.00`` → ``1250.00``; numbers are read through ``str``."""
    if isinstance(value, str):
        return value.strip().replace("$", "").replace(",", "")
    if isinstance(value, float | int) and not isinstance(value, bool):
        return str(value)
    return value


GroupCode = Annotated[Literal["CO", "PR", "OA", "PI", "CR"], BeforeValidator(_code)]
"""Claim adjustment group code (X12 CAS01)."""
CarcCode = Annotated[
    str, BeforeValidator(_code), StringConstraints(pattern=r"^(?:\d{1,3}|[A-Z]\d{1,2})$")
]
"""Claim adjustment reason code: ``197``, ``45``, ``B7``, ``P12``."""
RarcCode = Annotated[str, BeforeValidator(_code), StringConstraints(pattern=r"^(?:MA|M|N)\d{1,3}$")]
"""Remittance advice remark code: ``N286``, ``M15``, ``MA130``."""
ProcedureCode = Annotated[
    str, BeforeValidator(_code), StringConstraints(pattern=r"^(?:\d{4}[0-9FTU]|[A-Z]\d{4})$")
]
"""CPT (``99213``, ``0001F``) or HCPCS Level II (``J1100``)."""
Money = Annotated[
    Decimal, BeforeValidator(_amount), Field(max_digits=12, decimal_places=2, ge=-(10**9), le=10**9)
]
"""A dollar amount with at most two decimals."""
PayerName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


def _iso_date(value: object) -> object:
    """Only ``YYYY-MM-DD`` text (or a date) is a date: never a timestamp, never a datetime."""
    if isinstance(value, str) and not _ISO_DATE.fullmatch(value.strip()):
        raise ValueError("a date is written YYYY-MM-DD")
    if isinstance(value, int | float):
        # Pydantic reads a number as a Unix timestamp. A ValueError, not a TypeError: only a
        # ValueError becomes a validation error, so the value reads as unreadable.
        raise ValueError("a number is not a date")  # noqa: TRY004
    return value.strip() if isinstance(value, str) else value


_ISO_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IsoDate = Annotated[date, BeforeValidator(_iso_date)]
"""A calendar date written ``YYYY-MM-DD`` (US-6.3 review: ``1760486400`` is not a date)."""
ClaimNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,49}$")
]
"""The payer's claim control number (X12 CLP07), or the claim's own number."""

ValueT = TypeVar("ValueT")


class FieldStatus(StrEnum):
    """Where a field's value came from."""

    EXTRACTED = "extracted"
    """Read from a document and valid for the field."""
    UNREADABLE = "unreadable"
    """Missing or invalid in every document: highlighted for confirmation."""
    CONFIRMED = "confirmed"
    """Entered or confirmed by the biller."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Extracted(_Strict, Generic[ValueT]):
    """One field's value and status; an unreadable field has no value, the others have one.

    Attributes:
        value: The value, typed by the field.
        status: Where it came from.
    """

    value: ValueT | None = None
    status: FieldStatus

    @model_validator(mode="after")
    def _value_matches_status(self) -> Extracted[ValueT]:
        if (self.value is None) != (self.status is FieldStatus.UNREADABLE):
            raise ValueError("only an unreadable field has no value")
        return self


class Adjustment(_Strict):
    """One claim adjustment (X12 CAS): why part of the charge was not paid.

    Attributes:
        group_code: Who is responsible (``CO`` contractual, ``PR`` patient, …).
        carc: The reason code.
        amount: The amount adjusted.
    """

    group_code: Extracted[GroupCode]
    carc: Extracted[CarcCode]
    amount: Extracted[Money]


class ClaimLine(_Strict):
    """One service line.

    Attributes:
        procedure_code: CPT or HCPCS code.
        service_date: Date of service.
        billed_amount: Charge.
        paid_amount: Payment.
        adjustments: Line adjustments.
        rarc_codes: Line remark codes.
    """

    procedure_code: Extracted[ProcedureCode]
    service_date: Extracted[IsoDate]
    billed_amount: Extracted[Money]
    paid_amount: Extracted[Money]
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=99)
    rarc_codes: list[Extracted[RarcCode]] = Field(default_factory=list, max_length=99)


def _walk(value: object, path: str) -> Iterator[tuple[str, Extracted[Any]]]:
    if isinstance(value, Extracted):
        yield path, value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name), f"{path}.{name}" if path else name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}.{index}")


class CaseExtraction(_Strict):
    """A case's structured fields, from every source document.

    Attributes:
        payer_name: The payer.
        claim_id: The payer's claim number.
        billed_amount: Total charge.
        paid_amount: Total payment.
        denial_date: The date of the payer's decision, printed on the remittance or notice (US-6.3);
            unreadable in an extraction stored before it existed.
        adjustments: Claim-level adjustments.
        rarc_codes: Claim-level remark codes.
        lines: Service lines, in document order.
        other_claims: Claims an 835 held beyond the one read (each belongs in its own case).
        sources: The source documents read, by ID.
        itemized_by: The source the lines, adjustments, and remark codes came from.
        unread_sources: Sources that could not be decoded (a corrupt PDF or image), so the pane
            can say why their fields are missing.
    """

    payer_name: Extracted[PayerName]
    claim_id: Extracted[ClaimNumber]
    billed_amount: Extracted[Money]
    paid_amount: Extracted[Money]
    denial_date: Extracted[IsoDate] = Field(
        default_factory=lambda: Extracted[IsoDate](status=FieldStatus.UNREADABLE)
    )
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=99)
    rarc_codes: list[Extracted[RarcCode]] = Field(default_factory=list, max_length=99)
    lines: list[ClaimLine] = Field(default_factory=list, max_length=999)
    other_claims: int = Field(default=0, ge=0)
    sources: list[str] = Field(default_factory=list)
    itemized_by: str | None = None
    unread_sources: list[str] = Field(default_factory=list)

    def fields(self) -> Iterator[tuple[str, Extracted[Any]]]:
        """Yield every field with its path, in document order."""
        yield from _walk(self, "")

    def digest(self) -> str:
        """Return the SHA-256 of this extraction's JSON: any changed value changes it (US-6.1)."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def needs_confirmation(self) -> list[str]:
        """Return the paths of the unreadable fields, which the pane highlights."""
        return [path for path, field in self.fields() if field.status is FieldStatus.UNREADABLE]

    def confirm(self, path: str, value: str) -> CaseExtraction:
        """Return a copy in which the field at ``path`` holds ``value`` as ``confirmed``.

        Raises:
            KeyError: No field has that path.
            ValidationError: ``value`` is not valid for the field.
        """
        if path not in dict(self.fields()):
            raise KeyError(path)
        data = self.model_dump(mode="json")
        *parents, leaf = [int(part) if part.isdigit() else part for part in path.split(".")]
        node: Any = data
        for part in parents:
            node = node[part]
        node[leaf] = {"value": value, "status": FieldStatus.CONFIRMED.value}
        return CaseExtraction.model_validate(data)

    def keep_confirmed(self, previous: CaseExtraction) -> CaseExtraction:
        """Return a copy that keeps the biller's confirmed values from ``previous``.

        A claim-level value (payer, claim number, totals) is kept where its field still exists.
        A value inside the lines, adjustments, or remark codes is addressed by position, so it is
        kept only when they come from the same source in the same number of lines; otherwise a
        confirmation could land on another line, and the fresh values are shown instead.
        """
        current = dict(self.fields())
        same_items = (previous.itemized_by, len(previous.lines)) == (
            self.itemized_by,
            len(self.lines),
        )
        result = self
        for path, field in previous.fields():
            placed = same_items or path.split(".", 1)[0] not in _ITEMIZED
            if field.status is FieldStatus.CONFIRMED and path in current and placed:
                result = result.confirm(path, str(field.value))
        return result


class FieldConfirmation(_Strict):
    """``POST /cases/{case_id}/fields``: the biller's value for one field.

    Attributes:
        path: The field (see ``FIELD_PATH_PATTERN``).
        value: The value as typed; validated with the field's own type.
    """

    path: str = Field(pattern=FIELD_PATH_PATTERN)
    value: str = Field(min_length=1, max_length=200)


JobKind = Literal["extract", "diagnose", "draft"]
"""What a case job does: extraction (US-5.2), diagnosis (US-6.1), or drafting (US-7.1)."""


class JobStarted(_Strict):
    """``POST /cases/{case_id}/process``, ``/diagnose``, or ``/draft``: the job working on the case.

    Attributes:
        ok: Always ``True``.
        case_id: The case.
        job_id: The job; its progress arrives as ``plugin.claimcoach.case.progress`` events.
        kind: What the job does. A case runs one job at a time, so asking for a diagnosis while
            the case is being extracted returns the extraction job.
    """

    ok: Literal[True] = True
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    job_id: str = Field(pattern=r"^job_[0-9a-f]{16}$")
    kind: JobKind = "extract"


class JobEvents(_Strict):
    """``GET /jobs/{job_id}/events``: a job's progress events after a position.

    Attributes:
        ok: Always ``True``.
        job_id: The job.
        events: The events after the requested position, oldest first.
        finished: The job ended (its last event is ``done`` or ``failed``).
    """

    ok: Literal[True] = True
    job_id: str = Field(pattern=r"^job_[0-9a-f]{16}$")
    events: list[CaseProgressEvent]
    finished: bool


_MONEY: Final[TypeAdapter[Any]] = TypeAdapter(Money)
READERS: Final[dict[str, TypeAdapter[Any]]] = {
    "payer_name": TypeAdapter(PayerName),
    "claim_id": TypeAdapter(ClaimNumber),
    "billed_amount": _MONEY,
    "paid_amount": _MONEY,
    "amount": _MONEY,
    "group_code": TypeAdapter(GroupCode),
    "carc": TypeAdapter(CarcCode),
    "rarc_codes": TypeAdapter(RarcCode),
    "procedure_code": TypeAdapter(ProcedureCode),
    "service_date": TypeAdapter(IsoDate),
    "denial_date": TypeAdapter(IsoDate),
}
"""The value type of every field name in ``CaseExtraction``."""


def read_value(name: str, raw: object) -> dict[str, object]:
    """Return ``{"value", "status"}`` for ``raw`` read as the field ``name``.

    ``None``, a blank string, or a value that does not validate is ``unreadable``.

    Raises:
        KeyError: ``name`` is not a field name of ``CaseExtraction``.
    """
    adapter = READERS[name]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {"value": None, "status": FieldStatus.UNREADABLE.value}
    try:
        value = adapter.validate_python(raw)
    except ValidationError:
        return {"value": None, "status": FieldStatus.UNREADABLE.value}
    return {"value": adapter.dump_python(value, mode="json"), "status": FieldStatus.EXTRACTED.value}
