"""Where the two corpus scopes live.

Implements: US-4.1 (global scope under the Hermes root, user scope under the active profile's
plugin data dir), US-7.2 (each profile's short-lived ``exports`` folder, next to its user scope),
US-8.3 (the app-wide ``fine-tune`` folder), US-11.1 (the app-wide ``transcription`` folder).
Rules: BR-13, PC-6, PRD §9.

* ``global``: ``<hermes root>/plugin-data/claimcoach/global/``, shared by every profile.
* ``user``: ``plugin_data_dir("claimcoach")/user/``, i.e. ``<profile home>/plugin-data/claimcoach/
  user/``, where a profile's home is ``<root>/profiles/<name>`` and the default profile's home is
  the root itself.
* ``exports``: ``<profile home>/plugin-data/claimcoach/exports/``, a profile's exported drafts,
  each deleted 15 minutes after it is written (US-7.2).
* ``fine-tune``: ``<hermes root>/plugin-data/claimcoach/fine-tune/``, manager-approved,
  de-identified fine-tune exports and their approval log (US-8.3).
* ``transcription``: ``<hermes root>/plugin-data/claimcoach/transcription/``, the PHI-free queue of
  payer-call transcription jobs (US-11.1).

The gateway and the Hermes CLI resolve the *active* profile; the app-wide worker addresses a user
scope by a validated profile name instead, so a request can never point it at another directory.
"""

from __future__ import annotations

import errno
import os
import re
from pathlib import Path
from typing import Final

from claimcoach import PLUGIN_NAME
from claimcoach import paths as claimcoach_paths
from claimcoach.corpus.types import DEFAULT_PROFILE, PROFILE_PATTERN
from claimcoach.paths import app_data_dir, plugin_data_dir

__all__ = [
    "DATABASE",
    "EXPORTS_DIR",
    "FINE_TUNE_DIR",
    "GLOBAL_DIR",
    "INDEX",
    "TRANSCRIPTION_DIR",
    "USER_DIR",
    "InvalidProfileError",
    "active_profile",
    "exports_dirs",
    "fine_tune_dir",
    "global_scope_dir",
    "hermes_root",
    "profile_exports_dir",
    "profile_home",
    "profile_user_scope_dir",
    "transcription_dir",
    "user_scope_dir",
    "user_scopes",
]

GLOBAL_DIR: Final = "global"
USER_DIR: Final = "user"
EXPORTS_DIR: Final = "exports"
FINE_TUNE_DIR: Final = "fine-tune"
"""Where manager-approved fine-tune exports go, app-wide (US-8.3)."""
TRANSCRIPTION_DIR: Final = "transcription"
"""Where the transcription queue lives, app-wide (US-11.1)."""
DATABASE: Final = "corpus.sqlite3"
"""A directory is an initialized scope once it holds this file."""
INDEX: Final = "index.sqlite3"
"""The scope's vector index, next to its database."""

_PROFILE: Final = re.compile(PROFILE_PATTERN)


class InvalidProfileError(ValueError):
    """A profile name that could escape the Hermes root."""


def _secure(path: Path) -> Path:
    """Create ``path`` (0700) and return it; a symbolic link in its place is refused (US-8.3).

    Raises:
        OSError: ``path`` is a symbolic link, which would send exports wherever it points.
    """
    if path.is_symlink():
        raise OSError(errno.ELOOP, "a ClaimCoach folder must not be a symbolic link")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def hermes_root() -> Path:
    """Return the Hermes root: the directory that holds ``plugin-data`` and ``profiles``."""
    return claimcoach_paths.hermes_root().resolve()


def global_scope_dir(root: Path | None = None, *, create: bool = True) -> Path:
    """Return the global scope directory, created with mode 0700 unless ``create`` is false.

    Args:
        root: Hermes root; ``get_default_hermes_root()`` (via ``app_data_dir()``) by default.
        create: Create the directory; ``False`` only resolves the path.
    """
    data = app_data_dir() if root is None else root / "plugin-data" / PLUGIN_NAME
    path = data / GLOBAL_DIR
    return _secure(path) if create else path


def user_scope_dir() -> Path:
    """Return (and create, mode 0700) the active profile's user scope directory."""
    return _secure(plugin_data_dir() / USER_DIR)


def active_profile() -> str:
    """Return the active Hermes profile's name (``default`` for the root profile).

    Inside Hermes this compares ``get_hermes_home()`` with ``get_default_hermes_root()``; outside
    it, ``HERMES_HOME`` names a profile when it is ``<root>/profiles/<name>``.
    """
    try:
        from hermes_constants import get_default_hermes_root, get_hermes_home  # noqa: PLC0415
    except ImportError:
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()
        return home.name if home.parent.name == "profiles" else DEFAULT_PROFILE
    home, root = Path(get_hermes_home()).resolve(), Path(get_default_hermes_root()).resolve()
    return DEFAULT_PROFILE if home == root else home.name


def profile_home(profile: str, root: Path | None = None) -> Path:
    """Return a profile's Hermes home under ``root`` (default: ``hermes_root()``).

    Raises:
        InvalidProfileError: ``profile`` is not a Hermes profile name.
    """
    if not _PROFILE.fullmatch(profile):
        raise InvalidProfileError("invalid profile name")
    base = root or hermes_root()
    return base if profile == DEFAULT_PROFILE else base / "profiles" / profile


def profile_user_scope_dir(profile: str, root: Path | None = None, *, create: bool = True) -> Path:
    """Return ``profile``'s user scope directory, created with mode 0700 unless ``create`` is false.

    The same path Hermes' ``plugin_data_dir("claimcoach")`` gives while ``profile`` is active.

    Raises:
        InvalidProfileError: ``profile`` is not a Hermes profile name.
    """
    path = profile_home(profile, root) / "plugin-data" / PLUGIN_NAME / USER_DIR
    return _secure(path) if create else path


def fine_tune_dir(root: Path | None = None) -> Path:
    """Return (and create, mode 0700) the app-wide fine-tune exports folder (US-8.3)."""
    data = app_data_dir() if root is None else root / "plugin-data" / PLUGIN_NAME
    return _secure(data / FINE_TUNE_DIR)


def transcription_dir(root: Path | None = None) -> Path:
    """Return (and create, mode 0700) the app-wide transcription queue folder (US-11.1)."""
    data = app_data_dir() if root is None else root / "plugin-data" / PLUGIN_NAME
    return _secure(data / TRANSCRIPTION_DIR)


def profile_exports_dir(profile: str, root: Path | None = None) -> Path:
    """Return (and create, mode 0700) ``profile``'s exports folder (US-7.2).

    Raises:
        InvalidProfileError: ``profile`` is not a Hermes profile name.
    """
    return _secure(profile_home(profile, root) / "plugin-data" / PLUGIN_NAME / EXPORTS_DIR)


def _profile_homes(base: Path) -> list[tuple[str, Path]]:
    """Every profile home under ``base``, by profile name, default first."""
    candidates = [(DEFAULT_PROFILE, base)]
    profiles = base / "profiles"
    if profiles.is_dir():
        candidates += sorted(
            (home.name, home)
            for home in profiles.iterdir()
            if home.is_dir() and _PROFILE.fullmatch(home.name) and home.name != DEFAULT_PROFILE
        )
    return candidates


def exports_dirs(root: Path | None = None) -> list[Path]:
    """Return every profile's existing exports folder under ``root`` (US-7.2)."""
    return [
        folder
        for _name, home in _profile_homes(root or hermes_root())
        if (folder := home / "plugin-data" / PLUGIN_NAME / EXPORTS_DIR).is_dir()
    ]


def user_scopes(root: Path | None = None) -> dict[str, Path]:
    """Return every initialized user scope under ``root``, by profile name, default first."""
    scopes: dict[str, Path] = {}
    for name, home in _profile_homes(root or hermes_root()):
        scope = home / "plugin-data" / PLUGIN_NAME / USER_DIR
        if (scope / DATABASE).is_file():
            scopes[name] = scope
    return scopes
