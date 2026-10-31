"""Model roles, states, and the REST bodies of the model routes.

Implements: US-2.1 (``ModelRole``), US-2.2 (``ModelState``, ``ModelStatus``), US-2.3 (``queued``
and ``queued_requests``), US-2.4 (``WeightsState``, ``DownloadRequest``, ``ConversionRequest``,
``AcquireResult``). Rules: ES-1 (Pydantic v2 for every REST body), ES-8, BR-1 (``confirm`` is
required), BR-14 (bodies carry roles and states only, never document text).

This module imports neither YAML nor process code so the gateway can use it (PC-4).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

__all__ = [
    "AcquireOutcome",
    "AcquireResult",
    "AcquireState",
    "ConversionRequest",
    "DownloadRequest",
    "ModelRole",
    "ModelState",
    "ModelStatus",
    "ModelsStatusResponse",
    "WeightsState",
]


class ModelRole(StrEnum):
    """What ClaimCoach uses a local model for (PRD §8)."""

    EXTRACTION = "extraction"
    PHI_DETECTION = "phi_detection"
    CLASSIFICATION = "classification"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    EXPLANATION = "explanation"
    DRAFTING = "drafting"
    TRANSCRIPTION = "transcription"


class ModelState(StrEnum):
    """Lifecycle state of the server behind a role."""

    UNLOADED = "unloaded"
    QUEUED = "queued"
    STARTING = "starting"
    READY = "ready"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"


WeightsState = Literal["present", "missing"]
"""Whether the role's model directory under ``MODELS_HOME`` holds a model."""

AcquireState = Literal["downloading", "converting", "failed"]
"""A running or failed download/conversion job for the role."""

AcquireOutcome = Literal["started", "in_progress", "present", "declined"]
"""What a download or conversion request did."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelStatus(_Strict):
    """One role as the settings page sees it.

    Attributes:
        role: The role.
        state: State of the server that serves the role.
        port: Loopback port of that server.
        pid: Server process ID while it runs.
        queued_requests: Requests waiting on the memory guard for this server.
        tier_b: Size tier in billions of parameters.
        model_dir: Model directory, relative to ``MODELS_HOME``.
        weights: Whether that directory holds a model.
        source_present: For converted roles, whether the conversion source is present.
        venv_present: Whether the role's venv has an interpreter.
        acquire: Running or failed download/conversion job, if any.
    """

    role: ModelRole
    state: ModelState
    port: int
    pid: int | None = None
    queued_requests: int = Field(default=0, ge=0)
    tier_b: int
    model_dir: str
    weights: WeightsState
    source_present: bool | None = None
    venv_present: bool
    acquire: AcquireState | None = None


class ModelsStatusResponse(_Strict):
    """``GET /models/status``.

    Attributes:
        ok: Always ``True`` for a success body.
        idle_timeout_s: Seconds of inactivity before a server is unloaded.
        models: One entry per role, in registry order.
    """

    ok: Literal[True] = True
    idle_timeout_s: float
    models: list[ModelStatus]


class DownloadRequest(_Strict):
    """``POST /models/download``: fetch what a role needs from Hugging Face.

    Attributes:
        role: The role to download for.
        confirm: The user's answer; ``False`` declines and nothing is fetched (BR-1). A JSON
            boolean only: ``"yes"`` or ``1`` is ``invalid_request``, never consent.
    """

    role: ModelRole
    confirm: StrictBool


class ConversionRequest(_Strict):
    """``POST /models/convert``: convert a role's source model to local MLX 4-bit.

    Attributes:
        role: A role declared with ``convert`` in ``models.yaml`` (the reranker).
        confirm: The user's answer; ``False`` declines and nothing runs. A JSON boolean only.
    """

    role: ModelRole
    confirm: StrictBool


class AcquireResult(_Strict):
    """Answer to a download or conversion request.

    Attributes:
        ok: Always ``True`` for a success body.
        role: The role.
        outcome: ``started`` (job launched), ``in_progress`` (a job already runs), ``present``
            (nothing to do), or ``declined`` (the user said no; nothing ran).
    """

    ok: Literal[True] = True
    role: ModelRole
    outcome: AcquireOutcome
