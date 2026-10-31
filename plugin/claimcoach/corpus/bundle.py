"""The global-corpus import format: rule cards, code entries, and letter templates.

Implements: US-4.3 (typed ``RuleCard``, ``CodeEntry``, ``LetterTemplate`` with required ``source``
and ``verified_on``; ``CorpusBundle``; ``parse_bundle`` for a local YAML or JSON file; the corpus
view with its ``stale`` flag). Rules: ES-1, BR-1 (a local file only; nothing is fetched), PRD §11
(rule cards carry source and verified-on dates; stale cards are flagged).

A bundle file::

    items:
      - kind: rule_card
        payer: Aetna
        topic: timely_filing
        title: Aetna timely filing limit
        body: Corrected claims within 180 days of the original determination.
        source: Aetna provider manual 2026, section 7.2
        verified_on: 2026-09-15

This module imports neither SQLite nor numpy, so the Hermes CLI validates a bundle before it
sends it to the worker.
"""

from __future__ import annotations

import os
import stat
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

__all__ = [
    "MAX_BUNDLE_BYTES",
    "STALE_AFTER_DAYS",
    "BundleError",
    "CodeEntry",
    "CorpusBundle",
    "CorpusItem",
    "CorpusViewItem",
    "CorpusViewResponse",
    "ImportResult",
    "LetterTemplate",
    "RuleCard",
    "is_stale",
    "parse_bundle",
]

STALE_AFTER_DAYS: Final = 180
"""A card verified longer ago than this is flagged stale in the corpus view."""

MAX_BUNDLE_BYTES: Final = 5 * 1024 * 1024
MAX_ITEMS: Final = 5000
_SUFFIXES: Final = frozenset({".yaml", ".yml", ".json"})

Key = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 ._&'()-]+$")]


class BundleError(ValueError):
    """The file is not a valid corpus bundle; the message names the problem, never content."""


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=200_000)
    source: str = Field(min_length=1, max_length=500)
    verified_on: date

    @field_validator("verified_on")
    @classmethod
    def _not_in_future(cls, value: date) -> date:
        # The manager's local date; one day of slack for a worker in another time zone.
        if value > date.today() + timedelta(days=1):
            raise ValueError("verified_on is in the future")
        return value


class RuleCard(_Item):
    """A payer rule: timely filing, appeal levels, required documents, or where to send.

    Attributes:
        kind: ``rule_card``.
        payer: Payer name (not PHI).
        topic: What the rule is about.
    """

    kind: Literal["rule_card"]
    payer: Key
    topic: Literal["timely_filing", "appeal_levels", "required_docs", "submission", "other"]

    @property
    def key(self) -> str:
        """``<payer>/<topic>``."""
        return f"{self.payer}/{self.topic}"


class CodeEntry(_Item):
    """A CARC, RARC, or group code with its explanation.

    Attributes:
        kind: ``code``.
        code_set: Which list the code is from.
        code: The code, e.g. ``197`` or ``N290`` or ``CO``.
    """

    kind: Literal["code"]
    code_set: Literal["CARC", "RARC", "GROUP"]
    code: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9]+$")

    @property
    def key(self) -> str:
        """``<code_set>/<code>``."""
        return f"{self.code_set}/{self.code.upper()}"


class LetterTemplate(_Item):
    """An appeal or corrected-claim letter template.

    Attributes:
        kind: ``letter_template``.
        template_id: Stable template name.
    """

    kind: Literal["letter_template"]
    template_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")

    @property
    def key(self) -> str:
        """The template ID."""
        return self.template_id


CorpusItem = Annotated[RuleCard | CodeEntry | LetterTemplate, Field(discriminator="kind")]


class CorpusBundle(BaseModel):
    """One import: every item is stored, or none is.

    Attributes:
        items: The items; keys are unique per kind.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[CorpusItem] = Field(min_length=1, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def _unique_keys(self) -> CorpusBundle:
        keys = [(item.kind, item.key) for item in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate item key in bundle")
        # The same cap as a bundle file, so a posted body cannot be larger than an imported one.
        if sum(len(item.body) + len(item.title) for item in self.items) > MAX_BUNDLE_BYTES:
            raise ValueError("bundle text is larger than 5 MiB")
        return self


def parse_bundle(path: Path) -> CorpusBundle:
    """Read and validate a local YAML or JSON bundle.

    Args:
        path: The bundle file (``.yaml``, ``.yml``, or ``.json``; at most 5 MiB).

    Returns:
        The validated bundle.

    Raises:
        BundleError: Wrong suffix, not a regular file, too large, unreadable, not YAML/JSON, or
            not a valid bundle.
            The message names the field that failed, never the file's content.
    """
    if path.suffix.lower() not in _SUFFIXES:
        raise BundleError("a bundle is a .yaml, .yml, or .json file")
    try:
        # O_NONBLOCK: opening a FIFO must not wait for a writer; it is refused below.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise BundleError("a bundle is a regular file")
            raw = handle.read(MAX_BUNDLE_BYTES + 1)  # bounded, even if the file grows
        if len(raw) > MAX_BUNDLE_BYTES:
            raise BundleError("bundle is larger than 5 MiB")
        data = yaml.safe_load(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise BundleError("bundle file cannot be read") from exc
    except yaml.YAMLError as exc:
        raise BundleError("bundle is not valid YAML or JSON") from exc
    try:
        return CorpusBundle.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "bundle"
        raise BundleError(f"invalid bundle at {where}: {first['type']}") from exc


def is_stale(verified_on: date, today: date) -> bool:
    """Return whether an item verified on ``verified_on`` is stale on ``today``."""
    return today - verified_on > timedelta(days=STALE_AFTER_DAYS)


class ImportResult(BaseModel):
    """What an import stored.

    Attributes:
        ok: Always ``True``.
        imported: Items stored per kind.
        chunks: Chunks embedded.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    imported: dict[str, int]
    chunks: int = Field(ge=0)


class CorpusViewItem(BaseModel):
    """One global item as the corpus view lists it.

    Attributes:
        kind: Item kind.
        key: Item key inside its kind.
        title: Title.
        source: Where it came from.
        verified_on: When it was last verified.
        stale: Verified more than ``STALE_AFTER_DAYS`` ago.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rule_card", "code", "letter_template"]
    key: str
    title: str
    source: str
    verified_on: date
    stale: bool


class CorpusViewResponse(BaseModel):
    """The global corpus view.

    Attributes:
        ok: Always ``True``.
        items: Every global item, by kind then key.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    items: list[CorpusViewItem]
