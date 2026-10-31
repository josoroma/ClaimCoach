"""Back up and restore both corpus scopes with SQLite's online backup API.

Implements: US-4.1 (corpus-import-reindex-backup-restore runbook: backup and restore). Rules:
BR-6 (a user-scope backup stays encrypted: pages are copied, never decrypted), BR-13.

A backup is ``<dest>/claimcoach-corpus-<UTC stamp>/{global, user-<profile>}/`` holding each
scope's ``corpus.sqlite3`` and ``index.sqlite3``, consistent even while the worker runs. Restore
replaces the scope files and needs the worker stopped. Uses only the standard library, so the
Hermes CLI runs it.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Final

from claimcoach.corpus.paths import (
    DATABASE,
    GLOBAL_DIR,
    INDEX,
    InvalidProfileError,
    global_scope_dir,
    profile_home,
    profile_user_scope_dir,
    user_scopes,
)
from claimcoach.corpus.types import utc_now

__all__ = ["BackupError", "backup", "restore"]

_FILES: Final = (DATABASE, INDEX)
_USER_PREFIX: Final = "user-"


class BackupError(ValueError):
    """The backup or restore cannot run; the message says why."""


def _copy_scope(source: Path, target: Path) -> None:
    """Copy both files of a scope from one read snapshot, so the index matches the database."""
    target.mkdir(mode=0o700, parents=True)
    for file in _FILES:
        (target / file).touch(mode=0o600)
    src = sqlite3.connect(f"file:{source / DATABASE}?mode=ro", uri=True, isolation_level=None)
    try:
        src.execute("ATTACH DATABASE ? AS idx", (f"file:{source / INDEX}?mode=ro",))
        src.execute("BEGIN")
        for schema in ("main", "idx"):
            src.execute(f"SELECT count(*) FROM {schema}.sqlite_master").fetchone()  # noqa: S608
        for schema, file in (("main", DATABASE), ("idx", INDEX)):
            dst = sqlite3.connect(target / file)
            try:
                src.backup(dst, name=schema)
            finally:
                dst.close()
        src.execute("COMMIT")
    finally:
        src.close()
    for file in _FILES:
        (target / file).chmod(0o600)


def _scope_dirs(root: Path) -> dict[str, Path]:
    """Every initialized scope under ``root``; resolving creates nothing."""
    scopes = {GLOBAL_DIR: global_scope_dir(root, create=False)}
    scopes.update({_USER_PREFIX + name: path for name, path in user_scopes(root).items()})
    return {name: path for name, path in scopes.items() if (path / DATABASE).is_file()}


def backup(root: Path, dest: Path) -> Path:
    """Copy every initialized scope under ``root`` into a new folder in ``dest``.

    A failed backup removes its partial folder, so no stray copy of case data is left behind.

    Returns:
        The backup folder (mode 0700; files mode 0600).

    Raises:
        BackupError: No scope is initialized, or the copy failed.
    """
    scopes = _scope_dirs(root)
    if not scopes:
        raise BackupError("no corpus scope to back up")
    folder = dest / f"claimcoach-corpus-{utc_now():%Y%m%dT%H%M%S%fZ}"
    try:
        for name, source in scopes.items():
            _copy_scope(source, folder / name)
    except (sqlite3.Error, OSError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise BackupError("the backup failed; nothing was kept") from exc
    folder.chmod(0o700)
    return folder


def _target(root: Path, name: str) -> Path:
    if name == GLOBAL_DIR:
        return global_scope_dir(root)
    return profile_user_scope_dir(name.removeprefix(_USER_PREFIX), root)


def restore(root: Path, folder: Path) -> list[str]:
    """Replace the scopes under ``root`` with the ones in a backup folder.

    The caller must have stopped the worker. Every scope name is validated before anything is
    replaced; each file is copied next to its target and then renamed over it, so a failed copy
    leaves the live scope as it was. A restored user scope needs the same profile's Keychain item,
    and audit entries written after the backup are replaced with the backup's.

    Returns:
        The scope folders restored (``global``, ``user-<profile>``).

    Raises:
        BackupError: ``folder`` holds no scope backup, names an invalid profile, or a copy failed.
    """
    entries = sorted(folder.iterdir()) if folder.is_dir() else []
    names = [
        entry.name
        for entry in entries
        if (entry.name == GLOBAL_DIR or entry.name.startswith(_USER_PREFIX))
        and all((entry / file).is_file() for file in _FILES)
    ]
    if not names:
        raise BackupError("no scope backup in that folder")
    for name in names:
        if name != GLOBAL_DIR:
            try:
                profile_home(name.removeprefix(_USER_PREFIX), root)
            except InvalidProfileError as exc:
                raise BackupError("the backup names an invalid profile") from exc
    for name in names:
        target = _target(root, name)
        try:
            for file in _FILES:
                staged = target / f"{file}.restoring"
                shutil.copy2(folder / name / file, staged)
                staged.chmod(0o600)
            for file in _FILES:
                for stale in (target / f"{file}-wal", target / f"{file}-shm"):
                    stale.unlink(missing_ok=True)
                (target / f"{file}.restoring").replace(target / file)
        except OSError as exc:
            for file in _FILES:
                (target / f"{file}.restoring").unlink(missing_ok=True)
            raise BackupError("the restore failed; the live scope was left as it was") from exc
    return names
