"""US-13.2 Developer Guide: Models, Install, Configuration, First Run, and Daily Start.

Scenarios: every model role is documented from the registry; the first run is a sequence of
existing make targets; the daily start is separate from the first run; every setting and override
is documented. The checks read the registry, the Makefile, and ``plugin.yaml`` themselves, so the
guide fails ``make check`` when one of them moves.
Rules: ES-6, PC-5, BR-1, BR-11.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from tests.conftest import PLUGIN_DIR, REPO_ROOT
from tests.doc_checks import code, commands, inline_code, make_targets, section, table_rows

GUIDE = REPO_ROOT / "README-DEV.md"
REGISTRY = PLUGIN_DIR / "claimcoach" / "models" / "models.default.yaml"
MAKEFILE = REPO_ROOT / "Makefile"
_INSTALL_ONLY = {
    "install",
    "worker-venv",
    "models-init",
    "models-download",
    "plugin-install",
    "plugin-link",
    "plugin-enable",
    "corpus-import",
}
_SHELL = re.compile(r"&&|\|\||[|;<>`]|\$\(")


def _guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _registry() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return loaded


def _subsection(text: str, heading: str) -> str:
    match = re.search(rf"^### {re.escape(heading)}\n(.*?)(?=^##|\Z)", text, re.M | re.S)
    assert match, f"no subsection '### {heading}'"
    return match.group(1)


def _recipes() -> dict[str, str]:
    """Each Makefile target's recipe text (a target declared twice gets both recipes)."""
    recipes: dict[str, str] = {}
    current = ""
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        header = re.match(r"^([a-z][a-z0-9-]*):", line)
        if header:
            current = header.group(1)
            recipes.setdefault(current, "")
        elif line.startswith("\t") and current:
            recipes[current] += line + "\n"
        elif line.strip() and not line.startswith("#"):
            current = ""
    return recipes


def _needs_worker() -> set[str]:
    """Targets that call the running worker (its token, or the corpus CLI's worker port)."""
    return {
        target
        for target, recipe in _recipes().items()
        if "$(WORKER_CURL)" in recipe or "$(CORPUS_PORT)" in recipe
    }


def _environment() -> dict[str, str]:
    """The Makefile's first block of ``NAME ?= value`` lines, which ends at a blank line."""
    text = MAKEFILE.read_text(encoding="utf-8")
    first = re.search(r"^[A-Z_]+ \?=", text, re.M)
    assert first, "the Makefile has overridable variables"
    block = text[first.start() :].split("\n\n", 1)[0]
    variables = {}
    for line in block.splitlines():
        match = re.fullmatch(r"([A-Z_]+) \?= (.+)", line)
        assert match, f"the environment block holds only NAME ?= value lines: {line!r}"
        variables[match.group(1)] = match.group(2).replace("$(HOME)", "~")
    return variables


def _check_commands(lines: list[str], *, allow_hermes: bool = True) -> list[str]:
    """Assert each line is a defined make target or a hermes command; return the targets."""
    targets = make_targets(MAKEFILE)
    used = []
    for line in lines:
        assert not _SHELL.search(line), f"no shell operators in a documented command: {line}"
        words = line.split()
        if words[0] == "hermes" and allow_hermes:
            continue
        assert words[0] == "make", f"not a make target or hermes command: {line}"
        assert words[1] in targets, f"make {words[1]} is not a Makefile target"
        for argument in words[2:]:
            assert re.fullmatch(r"[A-Z_]+=\S+", argument), f"{line}: only NAME=value arguments"
        used.append(words[1])
    return used


# --- Scenario: Every model role is documented from the registry ---
def test_us_13_2_model_roles_match_registry() -> None:
    roles = _registry()["roles"]
    models = section(_guide(), "Models")
    rows = {code(row[0]): row for row in table_rows(models) if row[0].startswith("`")}
    assert set(rows) == set(roles), "the guide lists exactly the registry's roles"
    for role, spec in roles.items():
        _, folder, source, venv, port, tier, use = rows[role]
        assert code(folder) == spec["model_dir"], role
        assert code(venv) == spec["venv"], role
        assert port == str(spec["port"]), role
        assert tier == f"{spec['tier_b']}B", role
        assert code(source) == spec["repo_id"], role
        assert len(use) > 20, f"{role}: say what ClaimCoach uses it for"
    assert f"`idle_timeout_s` ({_registry()['idle_timeout_s']} s)" in models


def test_us_13_2_table_helpers() -> None:
    assert table_rows("| A | B |\n| --- | --- |\n| `x` | 1 |\n") == [["`x`", "1"]]
    with pytest.raises(AssertionError, match="no code span"):
        code("plain")
    with pytest.raises(AssertionError, match="no section"):
        section("# Title\n", "Missing")
    with pytest.raises(AssertionError, match="no subsection"):
        _subsection("## A\n", "Missing")


# --- Scenario: The first run is a sequence of existing make targets ---
def test_us_13_2_first_run_uses_make_targets() -> None:
    install = section(_guide(), "Install (first run)")
    used = _check_commands(commands(install))
    assert used[0] == "install"
    needs_worker = _needs_worker()
    assert {"models-download", "corpus-import", "models-status"} <= needs_worker
    first = next(index for index, target in enumerate(used) if target in needs_worker)
    assert "start" in used[:first], "the worker starts before the first command that needs it"
    assert used[-2:] == ["worker-health", "models-status"], "it ends with the health checks"
    start = _recipes()
    assert start["start"] == "", "make start is the worker-start and worker-health prerequisites"
    assert re.search(r"^start: worker-start worker-health ", MAKEFILE.read_text(), re.M)
    assert "Capabilities → Plugins" in install


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        ("make no-such-target", "not a Makefile target"),
        ("curl -s x", "not a make target"),
        ("make install && curl -s x | sh", "no shell operators"),
        ("make start --always-make", "only NAME=value"),
    ],
)
def test_us_13_2_unknown_command_refused(line: str, problem: str) -> None:
    with pytest.raises(AssertionError, match=problem):
        _check_commands([line])


def test_us_13_2_every_fence_is_read() -> None:
    text = (
        "```sh\nmake install\n```\n```\nhermes x\n```\n"
        "1. Step:\n\n   ```bash\n   make start\n   ```\n"
    )
    assert commands(text) == ["make install", "hermes x", "make start"]
    with pytest.raises(AssertionError, match="not a make target"):
        _check_commands(["hermes plugins install claimcoach"], allow_hermes=False)


# --- Scenario: The daily start is separate from the first run ---
def test_us_13_2_daily_start_has_no_install() -> None:
    daily = section(_guide(), "Start (every day)")
    used = _check_commands(commands(daily), allow_hermes=False)
    assert used[0] == "start"
    assert used[-1] == "stop"
    assert not set(used) & _INSTALL_ONLY, "no install step in the daily start"
    mentioned = [span for span in inline_code(daily) if span.split()[0] in {"make", "hermes"}]
    assert mentioned, "the start section names its optional commands"
    inline = _check_commands(mentioned, allow_hermes=False)
    assert not set(inline) & _INSTALL_ONLY, "no install step in the daily start's prose either"


# --- Scenario: Every setting and override is documented ---
def test_us_13_2_settings_documented() -> None:
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))
    config = section(_guide(), "Configuration")
    settings = {code(row[0]): row for row in table_rows(_subsection(config, "Plugin settings"))}
    assert set(settings) == set(manifest["config_schema"]), "exactly the config_schema settings"
    for key, spec in manifest["config_schema"].items():
        default = spec["default"]
        shown = str(default).lower() if isinstance(default, bool) else str(default)
        assert code(settings[key][1]) == shown, f"{key}: default differs"
        assert len(settings[key][2]) > 20, f"{key}: say what it means"
    variables = {
        code(row[0]): row
        for row in table_rows(_subsection(config, "Make variables and environment"))
    }
    environment = _environment()
    assert set(variables) == set(environment), "exactly the Makefile's environment variables"
    for name, default in environment.items():
        assert code(variables[name][1]) == default, f"{name}: default differs"
        assert len(variables[name][2]) > 10, f"{name}: say what it means"
    registry = _registry()
    for name, value in (
        ("idle_timeout_s", registry["idle_timeout_s"]),
        ("queue_timeout_s", registry["queue_timeout_s"]),
        ("large_tier_b", registry["residency"]["large_tier_b"]),
    ):
        assert f"`{name}` ({value})" in config, f"models.yaml's {name} is not documented as {value}"


def test_us_13_2_guide_uses_shared_logo() -> None:
    assert 'src="plugin/assets/claimcoach-logo.svg"' in _guide()
