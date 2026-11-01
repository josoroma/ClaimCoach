"""Typed ClaimCoach settings and the manifest ``config_schema`` they render.

Implements: US-1.1 (typed settings mirrored in ``plugin.yaml``), US-3.5 (``richer_agent_access``,
off by default; ``load_settings()`` reads the values Hermes stores), US-4.5
(``load_retention_days(home)`` reads one profile's retention for the worker's purge), US-8.2
(``share_outcome_stats``, off by default; ``load_outcome_sharing(home)`` reads one profile's
opt-in for the manager's weekly summary). Rules:
ES-1 (one source of truth for config), BR-3, BR-7 (retention default), BR-11 (``MODELS_HOME`` and
the 18200-18219 port range).

Hermes stores the values under ``plugins.entries.claimcoach.settings`` and renders
``config_schema`` as the Settings → Plugins form, so the schema is generated from this model and a
test fails when ``plugin.yaml`` drifts from it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.logs import get_logger

__all__ = [
    "PORT_RANGE",
    "ClaimCoachSettings",
    "load_outcome_sharing",
    "load_retention_days",
    "load_settings",
]

_log = get_logger("claimcoach.settings")

PORT_RANGE: Final = range(18200, 18220)
"""Ports ClaimCoach owns: the worker takes the first, model servers take the rest (BR-11)."""

# Hermes config_schema type names for the JSON-schema types this model uses.
_HERMES_TYPES: Final = {"string": "str", "integer": "int", "boolean": "bool"}


class ClaimCoachSettings(BaseModel):
    """User-editable ClaimCoach settings.

    Attributes:
        models_home: Directory that holds model weights; read in place, never copied.
        retention_days: Days after case close before source documents are purged.
        richer_agent_access: Opt-in for richer agent access when the Hermes chat model is local
            (PRD §7.2). Off by default and shown in the statusbar. Its scope is an open question
            (SPECS.md US-3.5), so in v1 it grants nothing: agent tool results stay redacted.
        share_outcome_stats: Opt-in for this profile's de-identified outcomes (an outcome, a
            date, the payer's rule-card name, the denial reason, the codes) to reach the
            manager's weekly summary and the manager-approved fine-tune export (PRD §9, US-8.2).
            Off by default; turning it off excludes the profile from the next summary or export.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    models_home: str = Field(
        default="~/Models",
        min_length=1,
        description=(
            "Directory that holds local model weights (MODELS_HOME). Weights are never copied."
        ),
    )
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
    an unreadable or tampered config can only switch richer agent access *off*. Validation is all
    or nothing: one unknown or invalid key resets every setting to its default, and a fixed
    warning is logged. ``richer_agent_access`` must be a real boolean (``"yes"`` or ``1`` is
    invalid). Hermes' legacy ``plugins.entries.claimcoach.config`` subtree is not read.

    Returns:
        The validated settings.
    """
    try:
        from hermes_cli.config import load_config_readonly  # noqa: PLC0415
    except ImportError:
        return ClaimCoachSettings()
    entry = _mapping(_mapping(_mapping(load_config_readonly(), "plugins"), "entries"), PLUGIN_NAME)
    try:
        return ClaimCoachSettings.model_validate(dict(_mapping(entry, "settings")))
    except ValidationError:
        _log.warning("stored ClaimCoach settings are invalid; using the defaults")
        return ClaimCoachSettings()


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
    if "retention_days" not in stored:
        return ClaimCoachSettings().retention_days
    try:
        return ClaimCoachSettings.model_validate(
            {"retention_days": stored["retention_days"]}
        ).retention_days
    except ValidationError:
        _log.warning("a profile's retention_days is invalid; its retention purge is skipped")
        return None


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
