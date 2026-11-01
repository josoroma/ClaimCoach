"""The manager's weekly denial-pattern summary, built from opted-in profiles' outcomes.

Implements: US-8.2 (an ISO week's bounds in this Mac's time zone; ``build_weekly_summary``, the
counts and the overturn rate per payer and denial reason and per payer and code, which reads only
the de-identified outcomes of profiles whose ``share_outcome_stats`` is on). Rules: ES-1, BR-7,
BR-14 (the summary carries counts, enums, codes, rule-card payer names, and profile names; logs
carry error types only), PRD §9 (it never reads raw case documents: ``corpus.store.read_outcomes``
can read the ``outcomes`` table only, and needs no profile's key).
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Final, NamedTuple

from pydantic import ValidationError

from claimcoach.cases.diagnosis import DenialReason
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.paths import profile_home, user_scopes
from claimcoach.corpus.store import read_outcomes
from claimcoach.corpus.types import CaseOutcome, OutcomeRow, utc_now
from claimcoach.logs import get_logger
from claimcoach.outcomes.features import OutcomeFeatures
from claimcoach.outcomes.types import (
    ISO_WEEK,
    CategoryRow,
    CodeRow,
    OutcomeCounts,
    WeeklySummary,
)
from claimcoach.settings import load_outcome_sharing

__all__ = [
    "SharedOutcomes",
    "build_weekly_summary",
    "last_completed_week",
    "shared_outcomes",
    "week_bounds",
]

_log = get_logger("claimcoach.outcomes")


def _local_midnight(day: date, tz: tzinfo | None) -> datetime:
    """``day`` at 00:00 in ``tz``, or in this Mac's time zone (with its DST rules) by default."""
    midnight = datetime.combine(day, time())
    return midnight.astimezone() if tz is None else midnight.replace(tzinfo=tz)


def week_bounds(week: str, tz: tzinfo | None = None) -> tuple[datetime, datetime]:
    """Return ``week``'s first instant and the first instant after it, in ``tz``."""
    year, number = week.split("-W")
    monday = date.fromisocalendar(int(year), int(number), 1)
    return _local_midnight(monday, tz), _local_midnight(monday + timedelta(days=7), tz)


def last_completed_week(now: datetime, tz: tzinfo | None = None) -> str:
    """Return the ISO week before the one ``now`` falls in, judged in ``tz``."""
    local = now.astimezone() if tz is None else now.astimezone(tz)
    year, week, _ = (local.date() - timedelta(days=7)).isocalendar()
    return f"{year}-W{week:02d}"


def _features(row: OutcomeRow) -> OutcomeFeatures:
    """The row's snapshot; one recorded before US-8.2, or unreadable, groups as unknown."""
    if row.features is None:
        return OutcomeFeatures()
    try:
        return OutcomeFeatures.model_validate_json(row.features)
    except ValidationError:
        _log.warning("an outcome's stored features are invalid; it is counted as unclassified")
        return OutcomeFeatures()


def _counts(outcomes: Iterable[CaseOutcome]) -> dict[str, int]:
    tally = Counter(outcome.value for outcome in outcomes)
    return {outcome.value: tally[outcome.value] for outcome in CaseOutcome}


def _sort_key(name: str | None) -> tuple[bool, str]:
    return (name is None, name or "")


def _summarize(rows: list[OutcomeRow]) -> tuple[list[CategoryRow], list[CodeRow]]:
    categories: dict[tuple[str | None, DenialReason | None], list[CaseOutcome]] = {}
    codes: dict[tuple[str | None, str], list[CaseOutcome]] = {}
    for row in rows:
        features = _features(row)
        categories.setdefault((features.payer, features.denial_reason), []).append(row.outcome)
        for code in dict.fromkeys(features.codes):  # a case counts once per code
            codes.setdefault((features.payer, code), []).append(row.outcome)
    by_category = [
        CategoryRow(payer=payer, denial_reason=reason, **_counts(outcomes))
        for (payer, reason), outcomes in categories.items()
    ]
    by_code = [
        CodeRow(payer=payer, code=code, **_counts(outcomes))
        for (payer, code), outcomes in codes.items()
    ]
    by_category.sort(key=lambda r: (-r.total, _sort_key(r.payer), _sort_key(r.denial_reason)))
    by_code.sort(key=lambda r: (-r.total, _sort_key(r.payer), r.code))
    return by_category, by_code


LOCALTIME: Final = Path("/etc/localtime")
"""macOS links this to the zone file of the Mac's time zone (``…/zoneinfo/America/Chicago``)."""


def _zone_name(start: datetime, tz: tzinfo | None) -> str:
    """The zone's IANA name when known (``America/Chicago``), else its abbreviation at ``start``.

    An abbreviation is ambiguous (``CST``) and names only one side of a daylight-saving change.
    """
    if tz is not None:
        return str(tz)
    _, found, name = os.path.realpath(LOCALTIME).partition("/zoneinfo/")
    return name if found and name else start.tzname() or "local"


class SharedOutcomes(NamedTuple):
    """The outcomes of every profile that shares them, and which profiles were read.

    Attributes:
        rows: Their outcomes, profile by profile, each oldest first.
        profiles: The opted-in profiles read.
        not_shared: How many profiles have not opted in; nothing of theirs was opened.
        unreadable: Opted-in profiles whose outcomes could not be read.
    """

    rows: list[OutcomeRow]
    profiles: list[str]
    not_shared: int
    unreadable: list[str]


def shared_outcomes(
    root: Path,
    since: datetime,
    until: datetime,
    shares: Callable[[Path], bool] = load_outcome_sharing,
) -> SharedOutcomes:
    """Read the outcomes recorded in ``[since, until)`` of every opted-in profile under ``root``.

    The opt-in is checked before a profile's database is opened (US-8.2, US-8.3).
    """
    shared = SharedOutcomes([], [], 0, [])
    not_shared = 0
    for profile, directory in user_scopes(root).items():
        if not shares(profile_home(profile, root)):
            not_shared += 1
            continue
        try:
            shared.rows.extend(read_outcomes(directory, since, until))
        except CorpusError as exc:
            _log.warning("a profile's outcomes could not be read: %s", type(exc).__name__)
            shared.unreadable.append(profile)
            continue
        shared.profiles.append(profile)
    return shared._replace(not_shared=not_shared)


def build_weekly_summary(
    root: Path,
    week: str | None = None,
    *,
    now: datetime | None = None,
    tz: tzinfo | None = None,
    shares: Callable[[Path], bool] = load_outcome_sharing,
) -> WeeklySummary:
    """Summarize one week of outcomes from every opted-in profile under ``root``.

    Args:
        root: The Hermes root.
        week: The ISO week; the last completed week by default.
        now: The time to judge "last completed week" against.
        tz: The time zone weeks are judged in; this Mac's by default (design decision 4).
        shares: Whether a profile home opted in; ``settings.load_outcome_sharing``.

    Returns:
        The summary. A profile that has not opted in is counted in ``not_shared`` and nothing of
        it is opened; one whose outcomes cannot be read is named in ``unreadable``.

    Raises:
        ValidationError: ``week`` is not an ISO week that exists.
    """
    chosen = (
        last_completed_week(now or utc_now(), tz)
        if week is None
        else ISO_WEEK.validate_python(week)
    )
    start, end = week_bounds(chosen, tz)
    shared = shared_outcomes(root, start, end, shares)
    rows = shared.rows
    by_category, by_code = _summarize(rows)
    return WeeklySummary(
        week=chosen,
        starts_at=start,
        ends_at=end,
        timezone=_zone_name(start, tz),
        profiles=shared.profiles,
        not_shared=shared.not_shared,
        unreadable=shared.unreadable,
        totals=OutcomeCounts(**_counts(row.outcome for row in rows)),
        by_category=by_category,
        by_code=by_code,
    )
