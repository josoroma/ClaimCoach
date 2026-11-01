"""Typed ClaimCoach settings and the manifest ``config_schema`` they render.

Implements: US-1.1 (typed settings mirrored in ``plugin.yaml``), US-3.5 (``richer_agent_access``,
off by default; ``load_settings()`` reads the values Hermes stores), US-4.5
(``load_retention_days(home)`` reads one profile's retention for the worker's purge), US-8.2
(``share_outcome_stats``, off by default; ``load_outcome_sharing(home)`` reads one profile's
opt-in for the manager's weekly summary), US-11.1 (``transcription_start_hour`` and
``transcription_end_hour``; ``load_transcription_window(home)`` reads one profile's after-hours
window for the transcription scheduler), US-10.3 (``save_retention_days`` saves the active
profile's retention period with Hermes' own plugin-settings writer; ``stored_retention_days`` reads
it for the settings page the way the worker's purge reads it), US-14.2 (no ``models_home``
setting: settings belong to one profile, and the worker that reads the weights is shared by every
profile, so it reads ``MODELS_HOME``; a value a profile saved earlier is ignored, never a reason
to reset the others). Rules: ES-1 (one source of truth for config), BR-3, BR-7 (retention
default), BR-11 (the 18200-18219 port range).

Hermes stores the values under ``plugins.entries.claimcoach.settings`` and renders
``config_schema`` as the Settings → Plugins form, so the schema is generated from this model and a
test fails when ``plugin.yaml`` drifts from it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api.models import ErrorCode
from claimcoach.calls.window import DEFAULT_END_HOUR, DEFAULT_START_HOUR, TranscriptionWindow
from claimcoach.logs import get_logger

__all__ = [
    "PLUGIN_DIR",
    "PORT_RANGE",
    "RETIRED_SETTINGS",
    "ClaimCoachSettings",
    "SettingsError",
    "SettingsManagedError",
    "SettingsUnavailableError",
    "load_outcome_sharing",
    "load_retention_days",
    "load_settings",
    "load_transcription_window",
    "save_retention_days",
    "stored_retention_days",
]

_log = get_logger("claimcoach.settings")

PLUGIN_DIR: Final = Path(__file__).resolve().parents[1]
"""The plugin directory that holds ``plugin.yaml``, whose ``config_schema`` Hermes checks saves
against."""
PORT_RANGE: Final = range(18200, 18220)
"""Ports ClaimCoach owns: the worker takes the first, model servers take the rest (BR-11)."""

# Hermes config_schema type names for the JSON-schema types this model uses.
_HERMES_TYPES: Final = {"string": "str", "integer": "int", "boolean": "bool"}
RETIRED_SETTINGS: Final = frozenset({"models_home"})
"""Settings ClaimCoach no longer has (US-14.2). A profile may still store them; they are dropped
before validation, so they never reset the profile's other settings."""


class ClaimCoachSettings(BaseModel):
    """User-editable ClaimCoach settings.

    Attributes:
        retention_days: Days after case close before source documents are purged.
        richer_agent_access: Opt-in for richer agent access when the Hermes chat model is local
            (PRD §7.2). Off by default and shown in the statusbar. Its scope is an open question
            (SPECS.md US-3.5), so in v1 it grants nothing: agent tool results stay redacted.
        share_outcome_stats: Opt-in for this profile's de-identified outcomes (an outcome, a
            date, the payer's rule-card name, the denial reason, the codes) to reach the
            manager's weekly summary and the manager-approved fine-tune export (PRD §9, US-8.2).
            Off by default; turning it off excludes the profile from the next summary or export.
        transcription_start_hour: Local hour the after-hours window opens, when recorded payer
            calls are transcribed (US-11.1).
        transcription_end_hour: Local hour the window closes; before the start it wraps midnight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Days after a case closes before its source documents are purged.",
    )
    richer_agent_access: StrictBool = Field(
        default=False,
        description=(
            "Richer agent access when your Hermes model is local. Off by default and shown in the "
            "statusbar. Reserved: until its scope is decided, agent tool results stay redacted."
        ),
    )

    share_outcome_stats: StrictBool = Field(
        default=False,
        description=(
            "Share this profile's de-identified case outcomes (no documents, names, or IDs) with "
            "the manager's weekly summary and the manager-approved fine-tune export. Off by "
            "default; turn it off to stop sharing."
        ),
    )
    transcription_start_hour: int = Field(
        default=DEFAULT_START_HOUR,
        ge=0,
        le=23,
        description=(
            "Hour (0-23, this Mac's time) after which recorded payer calls are transcribed. The "
            "transcription model runs alone, so keep this outside working hours."
        ),
    )
    transcription_end_hour: int = Field(
        default=DEFAULT_END_HOUR,
        ge=0,
        le=23,
        description=(
            "Hour (0-23) at which call transcription stops starting new calls; before the start "
            "hour it means the next morning."
        ),
    )

    @classmethod
    def config_schema(cls) -> dict[str, dict[str, Any]]:
        """Render the ``plugin.yaml`` ``config_schema`` block from this model.

        Returns:
            Mapping of setting name to ``{type, default, description}`` as Hermes expects it.
        """
        properties: dict[str, dict[str, Any]] = cls.model_json_schema()["properties"]
        return {
            name: {
                "type": _HERMES_TYPES[spec["type"]],
                "default": spec["default"],
                "description": spec["description"],
            }
            for name, spec in properties.items()
        }


def _mapping(value: object, key: str) -> Mapping[str, Any]:
    child = value.get(key) if isinstance(value, Mapping) else None
    return child if isinstance(child, Mapping) else {}


def load_settings() -> ClaimCoachSettings:
    """Return the settings Hermes stores under ``plugins.entries.claimcoach.settings``.

    Outside the gateway, or when the stored values do not validate, the defaults are returned, so
    an unreadable or tampered config can only switch richer agent access *off*. Keys in
    ``RETIRED_SETTINGS`` are dropped first (US-14.2); then validation is all or nothing: one unknown
    or invalid key resets every setting to its default, and a fixed warning is logged.
    ``richer_agent_access`` must be a real boolean (``"yes"`` or ``1`` is invalid). Hermes' legacy
    ``plugins.entries.claimcoach.config`` subtree is not read.

    Returns:
        The validated settings.
    """
    try:
        from hermes_cli.config import load_config_readonly  # noqa: PLC0415
    except ImportError:
        return ClaimCoachSettings()
    entry = _mapping(_mapping(_mapping(load_config_readonly(), "plugins"), "entries"), PLUGIN_NAME)
    try:
        stored = _mapping(entry, "settings")
        return ClaimCoachSettings.model_validate(
            {key: value for key, value in stored.items() if key not in RETIRED_SETTINGS}
        )
    except ValidationError:
        _log.warning("stored ClaimCoach settings are invalid; using the defaults")
        return ClaimCoachSettings()


def _retention_of(stored: Mapping[str, Any]) -> int | None:
    """``retention_days`` validated on its own: the default when missing, ``None`` when invalid."""
    if "retention_days" not in stored:
        return ClaimCoachSettings().retention_days
    try:
        return ClaimCoachSettings.model_validate(
            {"retention_days": stored["retention_days"]}
        ).retention_days
    except ValidationError:
        return None


def stored_retention_days() -> int | None:
    """Return the active profile's ``retention_days`` as the worker's purge reads it (US-10.3).

    Unlike ``load_settings``, another invalid setting cannot change it, so the settings page shows
    the period the purge uses. Outside the gateway the default is returned.

    Returns:
        Days after case close, or ``None`` when the stored value is invalid (the purge then skips
        the profile).
    """
    try:
        from hermes_cli.config import load_config_readonly  # noqa: PLC0415
    except ImportError:
        return ClaimCoachSettings().retention_days
    entry = _mapping(_mapping(_mapping(load_config_readonly(), "plugins"), "entries"), PLUGIN_NAME)
    return _retention_of(_mapping(entry, "settings"))


_UNREADABLE: Final = object()
"""``_stored_settings``' answer when the profile's config cannot be read."""


def _stored_settings(home: Path) -> Mapping[str, Any] | object:
    """The ``plugins.entries.claimcoach.settings`` mapping of ``<home>/config.yaml``.

    The app-wide worker runs outside Hermes, so it reads the file itself. A missing file is an
    empty mapping (every setting at its default); a file that cannot be read or parsed is
    ``_UNREADABLE``.
    """
    try:
        config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return _UNREADABLE
    entry = _mapping(_mapping(_mapping(config, "plugins"), "entries"), PLUGIN_NAME)
    return _mapping(entry, "settings")


def load_retention_days(home: Path) -> int | None:
    """Return the ``retention_days`` a profile's ``<home>/config.yaml`` sets, for the purge.

    Deleting is irreversible, so this fails *closed*, unlike ``load_settings``: the value is
    validated on its own (another invalid setting cannot change it), a missing value is the
    default (90), and an unreadable file or an invalid value returns ``None`` so the caller skips
    that profile.

    Args:
        home: The profile's Hermes home.

    Returns:
        Days after case close, or ``None`` when the setting cannot be trusted.
    """
    stored = _stored_settings(home)
    if not isinstance(stored, Mapping):
        _log.warning("a profile's Hermes config cannot be read; its retention purge is skipped")
        return None
    days = _retention_of(stored)
    if days is None:
        _log.warning("a profile's retention_days is invalid; its retention purge is skipped")
    return days


def load_outcome_sharing(home: Path) -> bool:
    """Return whether a profile opted in to sharing its de-identified outcomes (US-8.2).

    Sharing is the exception, so anything but a stored ``share_outcome_stats: true`` reads as
    *not* shared: a missing value, an invalid one (``"yes"``, ``1``), or an unreadable config. The
    value is validated on its own, so another invalid setting cannot change it.

    Args:
        home: The profile's Hermes home.

    Returns:
        ``True`` only for an explicit opt-in.
    """
    stored = _stored_settings(home)
    if not isinstance(stored, Mapping):
        _log.warning("a profile's Hermes config cannot be read; its outcomes are not shared")
        return False
    try:
        return ClaimCoachSettings.model_validate(
            {"share_outcome_stats": stored.get("share_outcome_stats", False)}
        ).share_outcome_stats
    except ValidationError:
        _log.warning("a profile's share_outcome_stats is invalid; its outcomes are not shared")
        return False


def load_transcription_window(home: Path) -> TranscriptionWindow:
    """Return the after-hours window a profile's ``<home>/config.yaml`` sets (US-11.1).

    Anything but two valid, different hours reads as the default window (19 to 7), which is after
    hours, so a bad or unreadable setting can never move the transcription model into the working
    day. The two values are validated on their own, so another invalid setting cannot change them.

    Args:
        home: The profile's Hermes home.

    Returns:
        The window.
    """
    stored = _stored_settings(home)
    if not isinstance(stored, Mapping):
        _log.warning("a profile's Hermes config cannot be read; the default window is used")
        return TranscriptionWindow()
    try:
        return TranscriptionWindow(
            start_hour=stored.get("transcription_start_hour", DEFAULT_START_HOUR),
            end_hour=stored.get("transcription_end_hour", DEFAULT_END_HOUR),
        )
    except ValidationError:
        _log.warning("a profile's transcription window is invalid; the default window is used")
        return TranscriptionWindow()


class SettingsError(Exception):
    """A setting was not saved; ``code`` and ``status_code`` say how the gateway answers."""

    code: ClassVar[ErrorCode]
    status_code: ClassVar[int]


class SettingsUnavailableError(SettingsError):
    """Hermes' plugin-settings writer is not here (outside the gateway) or refused the value."""

    code: ClassVar[ErrorCode] = "settings_unavailable"
    status_code: ClassVar[int] = 503


class SettingsManagedError(SettingsError):
    """The install or the setting is administrator-managed."""

    code: ClassVar[ErrorCode] = "settings_managed"
    status_code: ClassVar[int] = 403


def save_retention_days(days: int) -> None:
    """Save the active profile's ``retention_days`` with Hermes' plugin-settings writer (US-10.3).

    ``hermes_cli.plugins_settings.save_plugin_settings`` is the writer the Settings → Plugins form
    uses: it checks the value against ``plugin.yaml``'s ``config_schema`` and holds Hermes' config
    lock. The worker's purge reads the profile's ``config.yaml`` on its next run.

    Args:
        days: Days after a case closes before its content is purged.

    Raises:
        SettingsUnavailableError: Outside the gateway, or Hermes refused or failed the save (a
            config it cannot parse, a file it cannot write).
        SettingsManagedError: The install or the setting is administrator-managed.
    """
    try:
        from hermes_cli.plugins_settings import save_plugin_settings  # noqa: PLC0415
    except ImportError as exc:
        raise SettingsUnavailableError from exc
    try:
        save_plugin_settings(PLUGIN_NAME, PLUGIN_DIR, {"retention_days": days})
    except PermissionError as exc:
        # Hermes raises its managed-install refusals without an errno; an unreadable file has one.
        if exc.errno is None:
            _log.warning("retention_days was not saved: the setting is managed")
            raise SettingsManagedError from None
        _log.warning("retention_days was not saved: %s", type(exc).__name__)
        raise SettingsUnavailableError from None
    except Exception as exc:  # noqa: BLE001 - a bad config.yaml raises parser errors with its text
        # Type only: Hermes' messages quote config lines, which may hold secrets (BR-14).
        _log.warning("retention_days was not saved: %s", type(exc).__name__)
        raise SettingsUnavailableError from None
