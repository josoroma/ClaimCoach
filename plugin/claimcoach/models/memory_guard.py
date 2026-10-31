"""Which ClaimCoach model servers may be resident at the same time.

Implements: US-2.3 (``ResidencyPolicy`` applied to the size-tier table derived from
``models.yaml``). Rules: BR-12 (never two >= 14B models resident; Voxtral only when nothing else is
loaded), NFR-7 (peak resident model memory within the PRD budget).

The rule is a pure function of specs so it can be checked exhaustively; ``ModelManager`` calls it
under its lock before every start and treats ``starting``, ``ready``, and ``stopping`` servers as
resident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from claimcoach.models.registry import ModelRegistry, ModelSpec, ResidencyPolicy

__all__ = ["MemoryGuard", "SizeTier"]


@dataclass(frozen=True, slots=True)
class SizeTier:
    """The memory-relevant facts of one server.

    Attributes:
        port: The server's port (its identity; roles on one port share it).
        tier_b: Size tier in billions of parameters.
        runs_alone: Must be the only resident server.
    """

    port: int
    tier_b: int
    runs_alone: bool

    @classmethod
    def of(cls, spec: ModelSpec) -> SizeTier:
        """Return the tier of the server described by ``spec``."""
        return cls(port=spec.port, tier_b=spec.tier_b, runs_alone=spec.runs_alone)


class MemoryGuard:
    """Decide whether a server may start next to the resident ones.

    Args:
        policy: Residency thresholds from ``models.yaml``.
    """

    def __init__(self, policy: ResidencyPolicy) -> None:
        """Store the policy."""
        self.policy = policy

    @classmethod
    def from_registry(cls, registry: ModelRegistry) -> MemoryGuard:
        """Build the guard ``models.yaml`` describes."""
        return cls(registry.residency)

    def is_large(self, tier: SizeTier) -> bool:
        """Return whether ``tier`` counts against the one-large-model limit."""
        return tier.tier_b >= self.policy.large_tier_b

    def blockers(self, candidate: SizeTier, resident: Sequence[SizeTier]) -> list[SizeTier]:
        """Return the resident servers that must be gone before ``candidate`` may start.

        Args:
            candidate: The server that wants to start.
            resident: Every other server that is starting, ready, or stopping.

        Returns:
            An empty list when ``candidate`` may start now.
        """
        others = [tier for tier in resident if tier.port != candidate.port]
        if candidate.runs_alone:
            return others
        alone = [tier for tier in others if tier.runs_alone]
        if alone:
            return alone
        if self.is_large(candidate):
            return [tier for tier in others if self.is_large(tier)]
        return []
