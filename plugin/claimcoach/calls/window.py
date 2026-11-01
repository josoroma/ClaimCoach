"""The after-hours window in which payer calls are transcribed.

Implements: US-11.1 (``TranscriptionWindow``: a start and an end hour in the Mac's local time; the
window wraps midnight; ``contains`` says whether a job may start, ``next_start`` when it may,
``remaining`` how long the window stays open).
Rules: ES-1 (Pydantic v2, ``extra="forbid"``, frozen), BR-12 (Voxtral runs alone, so it runs when
the biller is not working).

This module imports nothing heavier than Pydantic, so the settings module can use it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["DEFAULT_END_HOUR", "DEFAULT_START_HOUR", "TranscriptionWindow"]

DEFAULT_START_HOUR: Final = 19
DEFAULT_END_HOUR: Final = 7


class TranscriptionWindow(BaseModel):
    """Whole local hours in which a transcription job may start.

    Attributes:
        start_hour: First hour of the window (0-23, local time).
        end_hour: Hour the window ends (0-23, local time); before ``start_hour`` it wraps midnight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_hour: int = Field(default=DEFAULT_START_HOUR, ge=0, le=23)
    end_hour: int = Field(default=DEFAULT_END_HOUR, ge=0, le=23)

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.start_hour == self.end_hour:
            raise ValueError("the window must not be empty or the whole day")
        return self

    def contains(self, local: datetime) -> bool:
        """Return whether a job may start at ``local`` (the Mac's local time)."""
        hour = local.hour
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour

    def next_start(self, local: datetime) -> datetime:
        """Return ``local`` when it is inside the window, else the window's next start."""
        if self.contains(local):
            return local
        start = local.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        return start if start > local else start + timedelta(days=1)

    def remaining(self, local: datetime) -> timedelta:
        """Return how long the window stays open after ``local``; zero outside it."""
        if not self.contains(local):
            return timedelta(0)
        end = local.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        return end - local if end > local else end + timedelta(days=1) - local
