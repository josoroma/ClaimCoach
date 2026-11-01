"""US-9.3 Denial-Triage Skill.

Scenarios: the skill is registered under the plugin namespace; the skill content contains no PHI.
Also: the frontmatter is the source of the name and description, the playbook keeps the PHI
boundary, and the real Hermes ``skill_view`` serves it.
Rules: ES-4, BR-2, BR-3, PRD §7 (``skills/denial-triage/``: no PHI).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from claimcoach.agent import __main__ as agent_cli
from claimcoach.agent.skills import SKILL_NAME, SKILL_PATH, read_frontmatter, register_skills
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.validators import find_regex_spans
from tests.conftest import HERMES_ROOT, PLUGIN_DIR, REPO_ROOT
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, fake_phi_reply, leaked_strings, serve_phi, static_models
from tests.fakes.registrar import FakeRegistrar

SKILL_DIR = PLUGIN_DIR / "skills" / SKILL_NAME


def skill_files() -> list[Path]:
    return sorted(path for path in SKILL_DIR.rglob("*") if path.is_file())


def probe_agent(hermes_python: Path, tmp_path: Path, case_arg: str = "case_01") -> dict[str, Any]:
    """Run ``tests/hermes/probe_agent.py`` with ClaimCoach enabled in a throwaway home."""
    home = tmp_path / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    (home / "plugins" / "claimcoach").symlink_to(PLUGIN_DIR, target_is_directory=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["claimcoach"]}}))
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    completed = subprocess.run(
        [str(hermes_python), str(REPO_ROOT / "tests/hermes/probe_agent.py"), case_arg],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    payload: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    return payload


# --- Scenario: Skill is registered under the plugin namespace ------------------------------------


def test_us_9_3_skill_registered() -> None:
    registrar = FakeRegistrar()
    assert register_skills(registrar) == "denial-triage"
    (qualified,) = registrar.skills
    assert qualified == "claimcoach:denial-triage"
    entry = registrar.skills[qualified]
    assert entry["path"] == SKILL_PATH == SKILL_DIR / "SKILL.md"
    frontmatter = read_frontmatter(SKILL_PATH)
    assert entry["frontmatter"] == frontmatter
    assert entry["description"] == frontmatter["description"]
    assert frontmatter["name"] == SKILL_NAME
    assert "PHI-free" in entry["description"]


@pytest.mark.hermes
def test_us_9_3_real_hermes_skill_view(hermes_python: Path, tmp_path: Path) -> None:
    """Hermes v0.22.5 ``skill_view("claimcoach:denial-triage")`` with the plugin enabled."""
    skill = probe_agent(hermes_python, tmp_path)["skill"]
    assert skill["success"] is True, skill
    assert skill["name"] == "claimcoach:denial-triage"
    assert skill["readiness_status"] == "available"
    assert Path(skill["skill_dir"]) == SKILL_DIR
    # Hermes puts a one-line bundle note in front of the file, served in place (not copied).
    assert skill["content"].endswith(SKILL_PATH.read_text(encoding="utf-8"))
    assert skill["description"] == read_frontmatter(SKILL_PATH)["description"]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("# no frontmatter\n", ValueError),
        ("", ValueError),
        ("---\nname: x\n", ValueError),
        ("---\n- a list\n---\nbody\n", TypeError),
    ],
)
def test_us_9_3_frontmatter_errors(tmp_path: Path, text: str, error: type[Exception]) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(text)
    with pytest.raises(error):
        read_frontmatter(path)


# --- Scenario: Skill content contains no PHI -------------------------------------------------


async def test_us_9_3_skill_contains_no_phi() -> None:
    """The US-3.1 detector over every skill file: its regex validators and its model step.

    The fake PHI model answers the fixture's names and addresses; a span is kept only where its
    text occurs, so this proves that none of them and no regex-shaped identifier is in the skill.
    """
    files = skill_files()
    assert files == [SKILL_PATH], "a new skill file is scanned too: extend this test's notes"
    with FakeModelServer() as phi_model:
        serve_phi(phi_model, fake_phi_reply(*PHI_DOCUMENTS))
        detector = PhiDetector(static_models(phi_model.base_url))
        for path in files:
            text = path.read_text(encoding="utf-8")
            assert await detector.detect(text) == [], path.name
            assert find_regex_spans(text) == [], path.name
            assert leaked_strings(text, *PHI_DOCUMENTS) == [], path.name
        assert phi_model.requests, "the model step ran"


def test_us_9_3_playbook_keeps_the_phi_boundary() -> None:
    """The playbook tells the agent to stay on IDs, codes, and payer names (BR-2, BR-3)."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    for rule in (
        "Work only with case IDs, codes, and payer names",
        "Never ask the biller to paste an EOB",
        "ClaimCoach never sends, submits",
    ):
        assert rule in text
    for tool in ("claimcoach_case_summary", "claimcoach_explain_code", "claimcoach_payer_rules"):
        assert f"`{tool}`" in text


def test_us_9_3_cli_prints_the_skill() -> None:
    lines: list[str] = []
    assert agent_cli.main(["skill"], out=lines.append) == 0
    assert lines == [
        f"# claimcoach:denial-triage  ({SKILL_PATH})",
        SKILL_PATH.read_text(encoding="utf-8"),
    ]
