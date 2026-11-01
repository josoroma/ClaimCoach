"""Typed eval sets: the synthetic PHI set, the labeled denial set, and the manager's draft reviews.

Implements: US-12.1 (``PhiEvalSet``: the US-3.1 synthetic documents with the PHI seeded into each,
by category), US-12.2 (``DenialEvalSet``: de-identified denial cases labeled with their
``DenialReason``; ``DraftReviewSet``: each model draft beside the letter the manager approved),
US-12.3 (the denial set is also the latency benchmark: its documents are 835 text, letter text,
and EOB PDFs). Rules: ES-1 (every file is validated into a strict model), BR-14 (a load failure
says which file, never what it holds).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from claimcoach.cases.diagnosis import DenialReason
from claimcoach.redact.types import PhiCategory

__all__ = [
    "PRD_CATEGORIES",
    "DenialCase",
    "DenialDocument",
    "DenialEvalSet",
    "DocumentKind",
    "DraftReview",
    "DraftReviewSet",
    "EvalSetError",
    "PhiEvalDocument",
    "PhiEvalSet",
    "load_denial_set",
    "load_draft_reviews",
    "load_phi_set",
]

ItemId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
SetName = Annotated[str, StringConstraints(min_length=1, max_length=120)]
PRD_CATEGORIES: Final = frozenset(PhiCategory) - {PhiCategory.OTHER}
"""The seven categories a PHI set must seed: names, DOB, MRN, member ID, SSN, address, phone."""
MAX_SET_BYTES: Final = 32 * 1024 * 1024
"""Largest eval-set file read (the committed sets are a few hundred kilobytes)."""


class EvalSetError(ValueError):
    """An eval-set file is missing, too large, or not the expected shape."""

    def __init__(self, path: Path) -> None:
        """Name the file only; its content may be PHI-shaped."""
        super().__init__(f"eval set {path} is missing or not a valid eval set")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ModelHint(_Strict):
    text: str
    category: str


class PhiEvalDocument(_Strict):
    """One synthetic document of the PHI set.

    Attributes:
        id: Its ID in the set.
        kind: What it imitates (``eob``, ``denial_letter``, …).
        text: The document.
        phi: Every PHI string seeded into it, by category.
        model: What a perfect PHI model reports for it; offline tests serve this as the fake
            model's reply. The eval never reads it.
    """

    id: ItemId
    kind: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1)
    phi: dict[PhiCategory, list[Annotated[str, StringConstraints(min_length=1)]]]
    model: list[_ModelHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _seeded(self) -> PhiEvalDocument:
        # A seed the text does not hold would count as redacted without the redactor doing anything.
        for values in self.phi.values():
            for value in values:
                pattern = rf"(?<!\w){re.escape(value)}(?!\w)"
                if re.search(pattern, self.text, re.IGNORECASE) is None:
                    raise ValueError("a seeded value does not occur in its document")
        return self


class PhiEvalSet(_Strict):
    """The synthetic PHI eval set (PRD §4: names, DOB, MRN, member ID, SSN, address, phone).

    Attributes:
        name: The set's name (its file's stem).
        documents: Its documents.
    """

    name: SetName
    documents: list[PhiEvalDocument] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_category(self) -> PhiEvalSet:
        seeded = {category for document in self.documents for category in document.phi}
        if not seeded >= PRD_CATEGORIES:
            raise ValueError("the set does not seed every PHI category of PRD §4")
        return self


DocumentKind = Literal["era_835", "letter", "eob_pdf"]
"""How a benchmark document reaches the case: 835 text pasted, a letter uploaded as a text file,
or an EOB uploaded as a PDF rendered from its text."""


class DenialDocument(_Strict):
    """One source document of a denial case.

    Attributes:
        kind: How it is attached.
        text: Its text (the 835 segments, the letter, or the EOB page).
    """

    kind: DocumentKind
    text: str = Field(min_length=1, max_length=200_000)


class DenialCase(_Strict):
    """A de-identified denial case and the reason it was denied.

    Attributes:
        id: Its ID in the set.
        denial_reason: The label the classification must reach.
        documents: What the biller would attach, in order.
    """

    id: ItemId
    denial_reason: DenialReason
    documents: list[DenialDocument] = Field(min_length=1, max_length=8)

    @property
    def kinds(self) -> list[str]:
        """Its document kinds, in order."""
        return [document.kind for document in self.documents]


class DenialEvalSet(_Strict):
    """Labeled de-identified denial cases (US-12.2) and the latency benchmark (US-12.3).

    Attributes:
        name: The set's name.
        provenance: Where the cases and labels come from, and who reviewed them.
        cases: The cases, in run order.
    """

    name: SetName
    provenance: str = Field(min_length=1, max_length=500)
    cases: list[DenialCase] = Field(min_length=1)


class DraftReview(_Strict):
    """A model draft and the letter the manager approved from it.

    Attributes:
        id: Its ID in the set.
        denial_reason: The case's denial reason, when known; the report groups by it.
        draft: The letter as the model drafted it, before any edit.
        final: The letter the manager approved.
    """

    id: ItemId
    denial_reason: DenialReason | None = None
    draft: str = Field(min_length=1)
    final: str = Field(min_length=1)


class DraftReviewSet(_Strict):
    """The manager's review of appeal drafts (US-12.2).

    Attributes:
        name: The set's name.
        provenance: Where the drafts come from and who reviewed them.
        reviews: The reviews.
    """

    name: SetName
    provenance: str = Field(min_length=1, max_length=500)
    reviews: list[DraftReview] = Field(min_length=1)


_PHI_DOCUMENTS: Final = TypeAdapter(list[PhiEvalDocument])


def _read(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_SET_BYTES:
            raise EvalSetError(path)
        return path.read_bytes()
    except OSError as exc:
        raise EvalSetError(path) from exc


def load_phi_set(path: Path) -> PhiEvalSet:
    """Load the synthetic PHI set (a JSON list of documents, as US-3.1 generates it).

    Raises:
        EvalSetError: The file is missing, too large, or not a PHI set.
    """
    try:
        documents = _PHI_DOCUMENTS.validate_json(_read(path))
        return PhiEvalSet(name=path.stem, documents=documents)
    except ValidationError as exc:
        raise EvalSetError(path) from exc


def load_denial_set(path: Path) -> DenialEvalSet:
    """Load a labeled denial set.

    Raises:
        EvalSetError: The file is missing, too large, or not a denial set.
    """
    try:
        return DenialEvalSet.model_validate_json(_read(path))
    except ValidationError as exc:
        raise EvalSetError(path) from exc


def load_draft_reviews(path: Path) -> DraftReviewSet:
    """Load the manager's draft reviews.

    Raises:
        EvalSetError: The file is missing, too large, or not a review set.
    """
    try:
        return DraftReviewSet.model_validate_json(_read(path))
    except ValidationError as exc:
        raise EvalSetError(path) from exc
