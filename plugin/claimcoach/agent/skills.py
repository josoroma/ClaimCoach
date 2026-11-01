"""The ``denial-triage`` skill: ClaimCoach's PHI-free triage and explanation playbook.

Implements: US-9.3 (``register_skills`` registers ``plugin/skills/denial-triage/SKILL.md`` with
``ctx.register_skill``, so the agent loads it as ``skill_view("claimcoach:denial-triage")``).
Rules: BR-3 (the playbook works from case IDs, codes, and payer names only), BR-2 (it never asks
for documents in the chat), PRD §7 (``skills/denial-triage/``: no PHI).

Hermes derives the ``claimcoach:`` namespace from the plugin name and serves the file in place;
nothing is copied into ``~/.hermes/skills/``. The name and description come from the file's own
frontmatter, so the file is the one source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Protocol

import yaml

__all__ = [
    "SKILL_NAME",
    "SKILL_PATH",
    "SkillRegistrar",
    "read_frontmatter",
    "register_skills",
]

SKILL_NAME: Final = "denial-triage"
SKILL_PATH: Final = Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME / "SKILL.md"
"""``plugin/skills/denial-triage/SKILL.md``, next to the app package inside the plugin."""
_FENCE: Final = "---"


class SkillRegistrar(Protocol):
    """The slice of Hermes' ``PluginContext`` that skill registration uses."""

    def register_skill(  # noqa: D102 - mirrors Hermes' signature
        self,
        name: str,
        path: Path,
        description: str = "",
        frontmatter: Mapping[str, Any] | None = None,
    ) -> object: ...


def read_frontmatter(path: Path) -> dict[str, Any]:
    """Return the YAML frontmatter of a ``SKILL.md`` (the block between the first two ``---``).

    Raises:
        ValueError: The file does not start with a frontmatter block.
        TypeError: The frontmatter is not a mapping.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != _FENCE or _FENCE not in lines[1:]:
        raise ValueError("a SKILL.md starts with a --- frontmatter block")
    end = lines.index(_FENCE, 1)
    data = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(data, dict):
        raise TypeError("a SKILL.md frontmatter is a mapping")
    return data


def register_skills(ctx: SkillRegistrar, path: Path = SKILL_PATH) -> str:
    """Register the denial-triage skill with Hermes.

    Args:
        ctx: Hermes plugin context.
        path: The ``SKILL.md`` to register.

    Returns:
        The skill's bare name; Hermes serves it as ``claimcoach:<name>``.
    """
    frontmatter = read_frontmatter(path)
    name = str(frontmatter["name"])
    ctx.register_skill(
        name, path, description=str(frontmatter["description"]), frontmatter=frontmatter
    )
    return name
