"""Markdown helpers for the EPIC-13 documentation checks (US-13.2 to US-13.5).

Sections, table rows, code spans, shell commands, image references, and a link checker that
resolves relative links and anchors the way GitHub does: inside the repository, with exact case.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import REPO_ROOT

_FENCE = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", re.M | re.S)
_SEPARATOR = re.compile(r"^\|[\s|:-]+\|$")
_LINK_TARGETS = (
    re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)"),
    re.compile(r"""(?:src|href)=["']([^"']+)["']"""),
    re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", re.M),
)


def section(text: str, heading: str) -> str:
    """Return the body of the ``## heading`` section of ``text``, up to the next ``##`` heading.

    Args:
        text: A Markdown document.
        heading: The section's heading text, without the ``## ``.

    Returns:
        The section's lines after its heading.
    """
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"no section '## {heading}'"
    return match.group(1)


def table_rows(text: str) -> list[list[str]]:
    """Return the body rows of every Markdown table in ``text``, each as its stripped cells."""
    lines = text.splitlines()
    rows = []
    for index, line in enumerate(lines):
        if not line.startswith("|") or _SEPARATOR.match(line):
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if _SEPARATOR.match(following):
            continue  # the header row
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def code(cell: str) -> str:
    """Return the first inline-code span of a table cell (``\\`x\\``` → ``x``)."""
    match = re.search(r"`([^`]+)`", cell)
    assert match, f"no code span in {cell!r}"
    return match.group(1)


def without_fences(text: str) -> str:
    """``text`` with every fenced block removed."""
    return _FENCE.sub("", text)


def commands(text: str) -> list[str]:
    """Return every line of every fenced block in ``text`` (any info string), in order."""
    return [
        line.strip()
        for block in _FENCE.findall(text)
        for line in block.splitlines()
        if line.strip()
    ]


def inline_code(text: str) -> list[str]:
    """Return every inline-code span outside fenced blocks."""
    return re.findall(r"`([^`\n]+)`", without_fences(text))


def make_targets(makefile: Path) -> set[str]:
    """The targets ``makefile`` defines."""
    return set(re.findall(r"^([a-z][a-z0-9-]*):", makefile.read_text(encoding="utf-8"), re.M))


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    """The heading anchors of a Markdown file; headings inside fenced blocks are not headings."""
    text = without_fences(path.read_text(encoding="utf-8"))
    return {slug(heading) for heading in re.findall(r"^#{1,6} (.+)$", text, re.M)}


def images(text: str) -> list[tuple[str, str]]:
    """Every image of ``text`` as ``(alt, path)``: Markdown images and ``<img>`` tags."""
    found = re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", text)
    for tag in re.findall(r"<img\b[^>]*>", text):
        src = re.search(r"""src=["']([^"']+)["']""", tag)
        alt = re.search(r"""alt=["']([^"']*)["']""", tag)
        found.append((alt.group(1) if alt else "", src.group(1) if src else ""))
    return found


def _exists_exactly(path: Path, root: Path) -> bool:
    """Whether ``path`` exists under ``root`` with exactly this case in every part."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return False  # outside the repository
    current = root.resolve()
    for part in parts:
        if not current.is_dir() or part not in {child.name for child in current.iterdir()}:
            return False
        current = current / part
    return True


def broken_links(path: Path, root: Path = REPO_ROOT) -> list[str]:
    """Return the relative links and anchors of ``path`` that resolve to nothing.

    A link must stay inside ``root`` and match each file name's case. An anchor, alone or after a
    Markdown file, must be one of that file's headings.
    """
    text = without_fences(path.read_text(encoding="utf-8"))
    targets = [target for pattern in _LINK_TARGETS for target in pattern.findall(text)]
    broken = []
    for target in targets:
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            continue  # an absolute URL
        file, _, anchor = target.partition("#")
        linked = (path.parent / file) if file else path
        missing = bool(file) and not _exists_exactly(linked, root)
        checked = not missing and bool(anchor) and linked.suffix == ".md"
        unknown_anchor = checked and anchor not in anchors(linked)
        if missing or unknown_anchor:
            broken.append(target)
    return broken
