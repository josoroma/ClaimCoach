"""US-13.6 Diagram Text Stays Inside Its Container.

Scenarios: node text fits its box; labels and tags fit their chips; free text stays on the canvas
and off the nodes; an overflow is named. Widths come from ``tests/svg_layout.py``: diagram-design's
per-character budget or the PyMuPDF font metrics with a 20% margin for proportional fallbacks
(DejaVu on Linux), whichever is wider, so a system font standing in for Geist still fits. Every
container rect must belong to its group, and a text the estimate cannot see (children, a size or
transform attribute) is refused, so the checks fail closed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.svg_checks import SVG_NS
from tests.svg_layout import (
    Box,
    classes,
    container,
    fonts,
    free_texts,
    groups,
    inside,
    overlaps,
    own_texts,
    rect_box,
    text_box,
    view_box,
)

DIAGRAMS = sorted((REPO_ROOT / "docs" / "assets").glob("*.svg"))
NODE_PADDING = 8
CHIP_PADDING = 3
_CONTAINER_RECTS = {"node", "node-accent", "chip", "tag", "tab"}


def _load(path: Path) -> ET.Element:
    return ET.parse(path).getroot()  # noqa: S314 - ours, checked self-contained by US-13.4


def _name(node: ET.Element) -> str:
    return " / ".join(text.text or "" for text in own_texts(node))


def node_overflows(root: ET.Element) -> list[str]:
    """Each node text, or tag, that is not inside its node's box with 8px of padding all round."""
    styles = fonts(root)
    problems = []
    for node in groups(root, "node"):
        box, name = rect_box(container(node)), _name(node)
        for text in own_texts(node):
            if not inside(text_box(text, styles), box, NODE_PADDING, NODE_PADDING):
                problems.append(f"'{text.text}' runs past its node ({name})")
        for tag in node.findall(f"{SVG_NS}g"):
            if not inside(rect_box(container(tag)), box, NODE_PADDING, NODE_PADDING):
                problems.append(f"the tag of node ({name}) runs past it")
    return problems


def chip_overflows(root: ET.Element) -> list[str]:
    """Each chip or tag text outside its rect, and each chip or top-level tag rect that leaves the
    canvas or covers a node."""
    styles = fonts(root)
    canvas = view_box(root)
    nodes = {_name(node): rect_box(container(node)) for node in groups(root, "node")}
    in_nodes = {id(g) for node in groups(root, "node") for g in node.iter(f"{SVG_NS}g")}
    problems = []
    for kind in ("chip", "tag"):
        for group in groups(root, kind):
            box = rect_box(container(group))
            problems += [
                f"'{text.text}' runs past its {kind}"
                for text in own_texts(group)
                if not inside(text_box(text, styles), box, CHIP_PADDING)
            ]
            if id(group) in in_nodes:
                continue
            label = " ".join(text.text or "" for text in own_texts(group))
            if not inside(box, canvas):
                problems.append(f"the {kind} '{label}' leaves the canvas")
            problems += [
                f"the {kind} '{label}' covers node ({name})"
                for name, node in nodes.items()
                if overlaps(box, node)
            ]
    return problems


def free_text_problems(root: ET.Element) -> list[str]:
    """Each free text that leaves the viewBox, covers a node, chip, or tag, or starts inside the
    sequence frame and runs past it."""
    styles = fonts(root)
    canvas = view_box(root)
    shapes: dict[str, Box] = {
        f"node ({_name(node)})": rect_box(container(node)) for node in groups(root, "node")
    }
    for kind in ("chip", "tag"):
        for group in groups(root, kind):
            label = " ".join(text.text or "" for text in own_texts(group))
            shapes[f"{kind} '{label}'"] = rect_box(container(group))
    frames = [rect_box(r) for r in root.iter(f"{SVG_NS}rect") if "frame" in classes(r)]
    problems = []
    for text in free_texts(root):
        box = text_box(text, styles)
        if not inside(box, canvas):
            problems.append(f"'{text.text}' leaves the canvas")
        problems += [
            f"'{text.text}' covers {name}" for name, shape in shapes.items() if overlaps(box, shape)
        ]
        start = (box[0], (box[1] + box[3]) / 2)
        for frame in frames:
            starts_in = frame[0] <= start[0] <= frame[2] and frame[1] <= start[1] <= frame[3]
            if starts_in and not inside(box, frame):
                problems.append(f"'{text.text}' runs past the frame")
    return problems


def orphan_containers(root: ET.Element) -> list[str]:
    """Each node, chip, tag, or tab rect that is not the first rect of its group (legend samples
    aside): such a rect would hold texts no check sees."""
    owned = {
        id(container(group)) for kind in ("node", "chip", "tag") for group in groups(root, kind)
    }
    return [
        f"a {sorted(classes(rect) & _CONTAINER_RECTS)[0]} rect outside its group"
        for rect in root.iter(f"{SVG_NS}rect")
        if classes(rect) & _CONTAINER_RECTS and "sample" not in classes(rect)
        if id(rect) not in owned
    ]


def test_us_13_6_every_diagram_has_text() -> None:
    assert [path.name for path in DIAGRAMS] == [
        "flow-request.svg",
        "flow-stakeholder.svg",
        "flow-user.svg",
    ]
    for path in DIAGRAMS:
        root = _load(path)
        assert groups(root, "node"), f"{path.name}: no nodes"
        assert free_texts(root), f"{path.name}: no free text"
        assert orphan_containers(root) == []


# --- Scenario: Node text fits its box ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_6_node_text_fits(path: Path) -> None:
    assert node_overflows(_load(path)) == []


# --- Scenario: Labels and tags fit their chips ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_6_labels_fit_chips(path: Path) -> None:
    root = _load(path)
    assert groups(root, "chip") or groups(root, "tag"), "the diagram has labels or tags"
    assert chip_overflows(root) == []


# --- Scenario: Free text stays on the canvas and off the nodes ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_6_free_text_on_canvas(path: Path) -> None:
    assert free_text_problems(_load(path)) == []


# --- Scenario: An overflow is named ---
_STYLE = (
    "<style>text{font-family:Geist,sans-serif}"
    ".name{font-size:14px;font-weight:600}"
    ".sub{font-family:'Geist Mono',monospace;font-size:11px}"
    ".label{font-family:'Geist Mono',monospace;font-size:9px;letter-spacing:0.06em}"
    ".msg{font-family:'Geist Mono',monospace;font-size:9px}"
    ".callout{font-family:'Instrument Serif',serif;font-size:14px}</style>"
)


def _svg(body: str) -> ET.Element:
    return ET.fromstring(  # noqa: S314 - a literal
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">{_STYLE}{body}</svg>'
    )


def test_us_13_6_overflow_is_named() -> None:
    root = _svg(
        '<g class="node accent"><rect x="0" y="0" width="160" height="72"/>'
        '<g class="tag"><rect x="148" y="8" width="40" height="12"/></g>'
        '<text class="name" x="8" y="40">Global corpus</text>'
        '<text class="sub" x="8" y="58">rules · codes · templates</text></g>'
        '<g class="chip"><rect x="200" y="0" width="40" height="16"/>'
        '<text class="label" x="220" y="11" text-anchor="middle">REDACTED ONLY</text></g>'
        '<g class="chip"><rect x="100" y="60" width="80" height="16"/>'
        '<text class="label" x="140" y="71" text-anchor="middle">SEALED</text></g>'
        '<text class="callout" x="40" y="40">over a node</text>'
    )
    name = "Global corpus / rules · codes · templates"
    assert node_overflows(root) == [
        f"'rules · codes · templates' runs past its node ({name})",
        f"the tag of node ({name}) runs past it",
    ]
    assert chip_overflows(root) == [
        "'REDACTED ONLY' runs past its chip",
        f"the chip 'SEALED' covers node ({name})",
    ]
    assert free_text_problems(root) == [f"'over a node' covers node ({name})"]


def test_us_13_6_vertical_padding_is_checked() -> None:
    root = _svg(
        '<g class="node"><rect x="0" y="0" width="200" height="72"/>'
        '<text class="name" x="8" y="68">Agent tools</text></g>'
    )
    assert node_overflows(root) == ["'Agent tools' runs past its node (Agent tools)"]


def test_us_13_6_free_text_off_canvas_is_named() -> None:
    root = _svg(
        '<text class="callout" x="380" y="100">Nothing is sent to a payer.</text>'
        '<rect class="frame" x="20" y="120" width="120" height="60"/>'
        '<text class="msg" x="28" y="150">plugin.claimcoach.case.progress</text>'
        '<g class="chip"><rect x="300" y="150" width="40" height="16"/>'
        '<text class="label" x="320" y="161" text-anchor="middle">OK</text></g>'
        '<text class="callout" x="280" y="164">over a chip</text>'
    )
    assert free_text_problems(root) == [
        "'Nothing is sent to a payer.' leaves the canvas",
        "'plugin.claimcoach.case.progress' runs past the frame",
        "'over a chip' covers chip 'OK'",
    ]


@pytest.mark.parametrize(
    ("markup", "problem"),
    [
        ('<text class="name" x="8" y="40">r<tspan>ules</tspan></text>', "with children"),
        ('<text class="name" x="8" y="40" font-size="28">Agent</text>', "font-size"),
        ('<text class="name" x="8" y="40" transform="translate(9 0)">Agent</text>', "transform"),
    ],
)
def test_us_13_6_unmeasurable_text_is_refused(markup: str, problem: str) -> None:
    root = _svg(f'<g class="node"><rect x="0" y="0" width="200" height="72"/>{markup}</g>')
    with pytest.raises(AssertionError, match=problem):
        node_overflows(root)


def test_us_13_6_orphan_container_is_named() -> None:
    root = _svg('<rect class="chip" x="0" y="0" width="40" height="16"/>')
    assert orphan_containers(root) == ["a chip rect outside its group"]


@pytest.mark.parametrize(
    ("anchor", "x", "fits"),
    [("start", 8, True), ("middle", 80, True), ("end", 152, True), ("end", 60, False)],
)
def test_us_13_6_anchors_are_measured(anchor: str, x: int, fits: bool) -> None:
    root = _svg(
        f'<g class="node"><rect x="0" y="0" width="160" height="72"/>'
        f'<text class="name" x="{x}" y="40" text-anchor="{anchor}">Agent tools</text></g>'
    )
    assert (node_overflows(root) == []) is fits
