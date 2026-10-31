"""Typed ClaimCoach settings and the manifest ``config_schema`` they render.

Implements: US-1.1 (typed settings mirrored in ``plugin.yaml``). Rules: ES-1 (one source of truth
for config), BR-7 (retention default), BR-11 (``MODELS_HOME`` and the 18200-18219 port range).

Hermes stores the values under ``plugins.entries.claimcoach.settings`` and renders
``config_schema`` as the Settings → Plugins form, so the schema is generated from this model and a
test fails when ``plugin.yaml`` drifts from it.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PORT_RANGE", "ClaimCoachSettings"]

PORT_RANGE: Final = range(18200, 18220)
"""Ports ClaimCoach owns: the worker takes the first, model servers take the rest (BR-11)."""

# Hermes config_schema type names for the JSON-schema types this model uses.
_HERMES_TYPES: Final = {"string": "str", "integer": "int", "boolean": "bool"}


class ClaimCoachSettings(BaseModel):
    """User-editable ClaimCoach settings.

    Attributes:
        models_home: Directory that holds model weights; read in place, never copied.
        retention_days: Days after case close before source documents are purged.
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
