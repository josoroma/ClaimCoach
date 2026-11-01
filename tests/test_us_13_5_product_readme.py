"""US-13.5 Product README for Y Combinator.

Scenarios: README.md is the product page; the product claims come from the PRD; every README uses
the shared logo (and every relative link and anchor in it resolves inside the repository).
Rules: PRD §1 to §6, §7.2, §8, §9, §10.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.doc_checks import broken_links, images, inline_code, section, table_rows

README = REPO_ROOT / "README.md"
PRD = REPO_ROOT / "PRD.md"
READMES = sorted(REPO_ROOT.glob("README*.md"))
LOGO = "plugin/assets/claimcoach-logo.svg"
_COMMAND = re.compile(r"^(?:make|hermes|uv|npm|node|ln|git|python3?|curl|openspec|brew)\b")
_CAVEAT = (
    "None has\nyet run against the real local models or inside a live Hermes Desktop, and the "
    "release gates have\nnot run."
)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


# --- Scenario: README.md is the product page ---
def test_us_13_5_readme_is_product_page() -> None:
    text = _readme()
    for heading in (
        "The problem",
        "What ClaimCoach does",
        "Who it's for",
        "Why it runs on the Mac",
        "v1 targets",
        "Status",
    ):
        assert section(text, heading).strip(), f"{heading} is empty"
    assert "PHI never leaves the Mac" in text
    assert ("A ClaimCoach case, from denial to outcome", "docs/assets/flow-user.svg") in images(
        text
    )
    assert "](README-DEV.md)" in text, "the developer guide is one link away"
    assert _CAVEAT in section(text, "Status"), "the status says what has not been verified"
    assert "```" not in text, "no install or engineering steps"
    assert not re.search(r"^ {4,}\S", text, re.M), "no indented code blocks"
    commands = [span for span in inline_code(text) if _COMMAND.match(span)]
    assert commands == [], "no commands on the product page"


# --- Scenario: The product claims come from the PRD ---
def test_us_13_5_targets_match_prd() -> None:
    prd = table_rows(section(PRD.read_text(encoding="utf-8"), "4. Goals and success metrics"))
    ours = table_rows(section(_readme(), "v1 targets"))
    assert len(prd) == 5
    assert ours == prd, "README.md states PRD §4's goals, measures, and targets word for word"


# --- Scenario: Every README uses the shared logo ---
@pytest.mark.parametrize("path", READMES, ids=[path.name for path in READMES])
def test_us_13_5_readmes_share_logo_and_links_resolve(path: Path) -> None:
    logos = [
        src
        for alt, src in images(path.read_text(encoding="utf-8"))
        if "logo" in f"{alt} {src}".lower()
    ]
    assert logos == [LOGO], "one logo, the shared file"
    assert broken_links(path) == []


def test_us_13_5_link_check_finds_broken_links(tmp_path: Path) -> None:
    (tmp_path / "other.md").write_text("# Other\n\n## Real heading\n", encoding="utf-8")
    (tmp_path / "Pic.svg").write_text("<svg/>", encoding="utf-8")
    page = tmp_path / "README.md"
    page.write_text(
        "# Title\n\n```\n# Not a heading\n```\n\n"
        "[ok](#title) [gone](#nowhere) [fenced](#not-a-heading) [file](missing.md) "
        '[titled](other.md "t") [web](https://x.test) [here](other.md#real-heading) '
        "[renamed](other.md#old-heading) [outside](../outside.md) [case](pic.svg)\n"
        '<img src="also-missing.svg">\n\n[ref]: missing-ref.md\n',
        encoding="utf-8",
    )
    assert broken_links(page, root=tmp_path) == [
        "#nowhere",
        "#not-a-heading",
        "missing.md",
        "other.md#old-heading",
        "../outside.md",
        "pic.svg",
        "also-missing.svg",
        "missing-ref.md",
    ]


def test_us_13_5_images_finds_every_logo() -> None:
    text = '<img src="a.svg" alt="ClaimCoach logo">\n![second logo](b.png)\n<img src="c.svg">\n'
    assert images(text) == [("second logo", "b.png"), ("ClaimCoach logo", "a.svg"), ("", "c.svg")]


def test_us_13_5_both_readmes_present() -> None:
    assert [path.name for path in READMES] == ["README-DEV.md", "README.md"]
