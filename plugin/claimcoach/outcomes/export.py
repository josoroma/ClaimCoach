"""The manager-approved fine-tune export of de-identified case/outcome pairs.

Implements: US-8.3 (``export_fine_tune``: nothing is read or written without an
``ExportApproval``; one ``FineTuneRecord`` per labeled outcome of every opted-in profile, as JSON
Lines in the app-wide ``fine-tune`` folder; every approval is appended to ``approvals.jsonl``).
Rules: BR-7 and BR-14 (records are built from the de-identified outcome snapshot only, never from
case text, and each one passes the US-3.1 regex validators or is withheld; logs carry counts
only), BR-13 (state under the Hermes root's plugin data, owner-only), PRD §9 (explicit,
manager-approved, never automatic).
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from claimcoach.corpus.paths import fine_tune_dir
from claimcoach.corpus.types import OutcomeRow, utc_now
from claimcoach.logs import get_logger
from claimcoach.outcomes.features import OutcomeFeatures
from claimcoach.outcomes.summary import shared_outcomes
from claimcoach.outcomes.types import (
    FINE_TUNE_FORMAT,
    ExportNotApprovedError,
    FineTuneExport,
    FineTuneExportRequest,
    FineTuneRecord,
)
from claimcoach.redact.validators import find_regex_spans
from claimcoach.settings import load_outcome_sharing

__all__ = ["APPROVALS_FILE", "export_fine_tune", "fine_tune_record"]

APPROVALS_FILE: Final = "approvals.jsonl"
"""The append-only record of every approved export, next to the exports."""

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_END: Final = datetime(9999, 12, 31, tzinfo=UTC)
"""The end of the export window: a row "recorded" after a clock was set back is still read."""
_log = get_logger("claimcoach.outcomes")


def fine_tune_record(row: OutcomeRow) -> FineTuneRecord | None:
    """Return the training pair of one outcome, or ``None`` when it has no label or facts.

    An outcome is a pair only when it was recorded with a current diagnosis (the label) and what
    the classifier read (the input); older or unclassified outcomes are left out.
    """
    if row.features is None:
        return None
    try:
        features = OutcomeFeatures.model_validate_json(row.features)
    except ValidationError:
        return None
    if features.denial_reason is None or features.facts is None:
        return None
    return FineTuneRecord(
        format=FINE_TUNE_FORMAT,
        payer=features.payer,
        facts=features.facts,
        codes=features.codes,
        denial_reason=features.denial_reason,
        appeal_likelihood=features.appeal_likelihood,
        outcome=row.outcome,
    )


def _write_new(path: Path, data: bytes) -> None:
    """Write ``data`` to a new owner-only file through a temporary name; nothing left on failure."""
    partial = path.with_name(f".{path.name}.partial")
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def _open_log(path: Path) -> int:
    """Open the approval log for appending: a regular, owner-only file of this user, never a link.

    Opened before the export is written, so a log that cannot take the line stops the export
    before any file exists. ``O_NONBLOCK`` keeps a FIFO planted at the path from blocking.

    Raises:
        OSError: The log is a link, not a regular file, or not this user's.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        os.close(fd)
        raise OSError(errno.EPERM, "the approval log is not this user's regular file")
    os.fchmod(fd, 0o600)  # a copy restored with another mode is made owner-only again
    return fd


def export_fine_tune(
    root: Path,
    request: FineTuneExportRequest,
    *,
    now: datetime | None = None,
    shares: Callable[[Path], bool] = load_outcome_sharing,
) -> FineTuneExport:
    """Write every labeled, de-identified outcome of the opted-in profiles to a new JSONL file.

    Args:
        root: The Hermes root.
        request: The export request; it must carry an approval with ``approved: true``.
        now: When the export runs.
        shares: Whether a profile home opted in; ``settings.load_outcome_sharing``.

    Returns:
        Where the file is and what it holds.

    Raises:
        ExportNotApprovedError: No approval, or ``approved`` is false; nothing is read or written.
        OSError: The folder, the export, or the approval log could not be written; no export
            file is left behind, and no export is left unlogged.
    """
    approval = request.approval
    if approval is None or not approval.approved:
        raise ExportNotApprovedError
    when = now or utc_now()
    shared = shared_outcomes(root, _EPOCH, _END, shares)
    lines: list[str] = []
    unlabeled = withheld = 0
    for row in shared.rows:
        record = fine_tune_record(row)
        if record is None:
            unlabeled += 1
            continue
        text = record.model_dump_json()
        if find_regex_spans(text):  # a last guard: the snapshot is de-identified by construction
            withheld += 1
            continue
        lines.append(text)
    folder = fine_tune_dir(root)
    stamp = when.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"fine-tune-{stamp}-{secrets.token_hex(4)}.jsonl"
    log = _open_log(folder / APPROVALS_FILE)
    with os.fdopen(log, "a", encoding="utf-8") as handle:
        _write_new(target, "".join(f"{line}\n" for line in lines).encode())
        exported = FineTuneExport(
            path=str(target),
            filename=target.name,
            records=len(lines),
            unlabeled=unlabeled,
            withheld=withheld,
            profiles=shared.profiles,
            unreadable=shared.unreadable,
            approved_by=approval.manager,
            approved_at=when,
        )
        entry = exported.model_dump_json(
            include={"filename", "records", "profiles", "approved_by", "approved_at"}
        )
        try:
            handle.write(entry + "\n")
            handle.flush()
        except BaseException:
            target.unlink(missing_ok=True)  # an export is never left unlogged
            raise
    _log.info(
        "fine-tune export wrote %d records (%d unlabeled, %d withheld)",
        len(lines),
        unlabeled,
        withheld,
    )
    return exported
