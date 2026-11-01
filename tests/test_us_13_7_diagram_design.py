"""US-13.7 Diagrams in the diagram-design Style.

Scenarios: the background is transparent; connectors are orthogonal on a 4px grid; nodes and
labels follow the primitives; each diagram stays within its complexity budget. The rules are
diagram-design's (github.com/cathrynlavery/diagram-design: ``primitives-core.md``,
``style-guide.md``, ``layout-budget.md``, ``type-sequence.md``); legend samples (class ``sample``)
are not counted.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

import pytest

from tests.svg_checks import SVG_NS
from tests.svg_layout import (
    computed,
    css_rules,
    fonts,
    groups,
    media_rules,
    own_texts,
    path_points,
    rect_box,
    style_of,
    text_box,
    view_box,
)
from tests.test_us_13_6_text_fit import DIAGRAMS

BOXES = {"node", "node-accent", "zone", "zone-accent", "chip", "tag", "tab", "frame"}
SEQUENCE = "flow-request.svg"


def _load(path: Path) -> ET.Element:
    return ET.parse(path).getroot()  # noqa: S314 - ours, checked self-contained by US-13.4


def _classes(element: ET.Element) -> set[str]:
    return set((element.get("class") or "").split())


def _drawn(root: ET.Element, tag: str) -> list[ET.Element]:
    """Every ``tag`` element that is not a legend sample."""
    return [e for e in root.iter(f"{SVG_NS}{tag}") if "sample" not in _classes(e)]


def connectors(root: ET.Element) -> list[ET.Element]:
    """Every arrow the diagram draws (legend samples excluded)."""
    return [e for e in _drawn(root, "path") if _classes(e) & {"arrow", "arrow-accent"}]


def _shape_box(element: ET.Element) -> tuple[float, float, float, float] | None:
    """The bounding box of a rect or a path's points, else ``None``."""
    if element.tag == f"{SVG_NS}rect":
        return rect_box(element)
    if element.tag == f"{SVG_NS}path":
        points = [point for _, point in path_points(element.get("d", ""))]
        xs, ys = [x for x, _ in points], [y for _, y in points]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def background_problems(root: ET.Element) -> list[str]:
    """Each way the diagram could paint its canvas: a filled shape covering the viewBox, a CSS or
    inline ``background``, or a light-page rule that sets more than tokens."""
    canvas = view_box(root)
    problems = []
    for element in root.iter():
        box = _shape_box(element)
        if box is None or computed(root, element).get("fill", "black") == "none":
            continue
        if (
            box[0] <= canvas[0]
            and box[1] <= canvas[1]
            and box[2] >= canvas[2]
            and box[3] >= canvas[3]
        ):
            problems.append(f"a {element.tag.removeprefix(SVG_NS)} paints the whole canvas")
    style = style_of(root)
    if re.search(r"(?<![\w-])background\s*:", style):
        problems.append("the style sets a background")
    if "background" in (root.get("style") or ""):
        problems.append("the root sets a background")
    for selector, body in media_rules(style, "(prefers-color-scheme: light)"):
        problems += [
            f"{selector} {name} on a light page" for name in body if not name.startswith("--")
        ]
    return problems


# --- Scenario: The background is transparent ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_7_background_transparent(path: Path) -> None:
    assert background_problems(_load(path)) == []


def test_us_13_7_painted_backgrounds_are_refused() -> None:
    root = ET.fromstring(  # noqa: S314 - a literal
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" style="background:red">'
        "<style>:root{--c:oklch(1 0 0)}.dark{--c:oklch(0 0 0)}svg{background:var(--c)}"
        "path.p{fill:var(--c)}rect.zone{fill:none}"
        "@media (prefers-color-scheme: light){:root.dark{--c:oklch(1 0 0)}rect.zone{fill:var(--c)}}"
        '</style><path class="p" d="M0 0H100V50H0Z"/>'
        '<rect class="zone" x="0" y="0" width="100" height="50"/>'
        "</svg>"
    )
    assert background_problems(root) == [
        "a path paints the whole canvas",
        "the style sets a background",
        "the root sets a background",
        "rect.zone fill on a light page",
    ]


def path_problems(d: str) -> list[str]:
    """What breaks diagram-design's connector rules in one path: any command but absolute M, H, V,
    and A; a sharp or diagonal turn; an elbow that is not a quarter-arc with 6 <= r <= 8 turning
    the way the path goes; points off the 4px grid."""
    problems = []
    if re.search(r"[^MHVA\d\s.,-]", d):
        problems.append("uses a command other than M, H, V, or A")
    points = path_points(d)
    if not points or points[0][0] != "M":
        problems.append("does not start with M")
    arcs = iter(re.findall(r"A\s*([\d.]+)[\s,]+([\d.]+)[\s,]+[\d.]+[\s,]+[01][\s,]+([01])", d))
    heading: tuple[float, float] | None = None
    for (_, (x0, y0)), (command, (x1, y1)) in pairwise(points):
        dx, dy = x1 - x0, y1 - y0
        if command == "A":
            rx, ry, sweep = next(arcs)
            radius = float(rx)
            if rx != ry or not 6 <= radius <= 8 or not abs(dx) == abs(dy) == radius:
                problems.append(f"an elbow of radius {radius:g} is not a 6-8 quarter-arc")
            elif heading is not None:
                # Leaving along ``heading``, the arc ends turned 90 degrees; the cross product of
                # the heading and the chord says which way (clockwise on screen is sweep 1).
                clockwise = heading[0] * dy - heading[1] * dx > 0
                if clockwise != (sweep == "1"):
                    problems.append(f"the elbow at ({x0:g}, {y0:g}) turns against the path")
            heading = None
            continue
        if dx and dy:
            problems.append(f"a diagonal from ({x0:g}, {y0:g}) to ({x1:g}, {y1:g})")
        direction = (float((dx > 0) - (dx < 0)), float((dy > 0) - (dy < 0)))
        if heading is not None and direction != heading and command != "M":
            problems.append(f"a sharp corner at ({x0:g}, {y0:g})")
        heading = direction
    problems += [f"({x:g}, {y:g}) is off the 4px grid" for _, (x, y) in points if x % 4 or y % 4]
    return problems


# --- Scenario: Connectors are orthogonal on a 4px grid ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_7_connectors_orthogonal_on_grid(path: Path) -> None:
    root = _load(path)
    assert connectors(root), f"{path.name}: no connectors"
    for arrow in connectors(root):
        assert path_problems(arrow.get("d", "")) == [], arrow.get("d")
    for rect in _drawn(root, "rect"):
        if _classes(rect) & BOXES:
            for attribute in ("x", "y", "width", "height"):
                value = float(rect.get(attribute, "0"))
                assert value % 4 == 0, f"{path.name}: rect {attribute}={value} is off the grid"


@pytest.mark.parametrize(
    ("d", "problem"),
    [
        ("M0 0L12 12", "uses a command other than M, H, V, or A"),
        ("M248 100l24 32", "uses a command other than M, H, V, or A"),
        ("M520 136C520 200 372 180 372 248", "uses a command other than M, H, V, or A"),
        ("M0 0H10", "(10, 0) is off the 4px grid"),
        ("M0 0H8V24", "a sharp corner at (8, 0)"),
        ("M0 0H8A12 12 0 0 1 20 12V24", "an elbow of radius 12 is not a 6-8 quarter-arc"),
        ("M0 0H8A4 4 0 0 1 12 4V24", "an elbow of radius 4 is not a 6-8 quarter-arc"),
        ("M0 0H8A8 8 0 0 1 20 8V24", "an elbow of radius 8 is not a 6-8 quarter-arc"),
        ("M0 0H8A8 8 0 0 0 16 8V24", "the elbow at (8, 0) turns against the path"),
        ("H8", "does not start with M"),
    ],
)
def test_us_13_7_diagonals_and_off_grid_are_refused(d: str, problem: str) -> None:
    assert problem in path_problems(d)
    assert path_problems("M0 0H8A8 8 0 0 1 16 8V24") == []
    assert path_problems("M544 136V168A8 8 0 0 1 536 176H380A8 8 0 0 0 372 184V248") == []


# --- Scenario: Nodes and labels follow the primitives ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_7_primitives_followed(path: Path) -> None:
    root = _load(path)
    stem = path.stem
    rules = dict(css_rules(style_of(root)))
    for box in ("node", "node-accent"):
        assert float(rules[f"rect.{box}"]["stroke-width"]) <= 1.2, "hairline borders"
    for node in groups(root, "node"):
        rect = node.find(f"{SVG_NS}rect")
        assert rect is not None
        assert float(rect.get("rx", "0")) <= 8, "corner radius at most 8"
    text = path.read_text(encoding="utf-8")
    assert "<filter" not in text, "no shadows or filters"
    assert "filter" not in "".join(f"{k}{v}" for body in rules.values() for k, v in body.items())
    for chip in groups(root, "chip"):
        (label,) = own_texts(chip)
        assert label.text == (label.text or "").upper(), f"'{label.text}': labels are uppercase"
        assert len(label.text or "") <= 14, f"'{label.text}': at most 14 characters"
    assert root.get("role") == "img"
    assert root.get("aria-labelledby") == f"{stem}-title {stem}-desc"
    title, desc = root.find(f"{SVG_NS}title"), root.find(f"{SVG_NS}desc")
    assert title is not None
    assert desc is not None
    assert title.get("id") == f"{stem}-title"
    assert desc.get("id") == f"{stem}-desc"
    assert root[0] is title, "the title comes first"
    for marker in root.iter(f"{SVG_NS}marker"):
        assert (marker.get("id") or "").startswith(f"{stem}-"), "IDs carry the diagram's name"


def test_us_13_7_sequence_labels_clear_other_lifelines() -> None:
    root = _load(next(path for path in DIAGRAMS if path.name == SEQUENCE))
    styles = fonts(root)
    lanes = [
        path_points(e.get("d", ""))[0][1][0]
        for e in root.iter(f"{SVG_NS}path")
        if "life" in _classes(e)
    ]
    messages = [e for e in root.iter(f"{SVG_NS}text") if e.get("class") == "msg"]
    assert len(messages) == len(connectors(root))
    top, bottom = (
        80,
        max(
            path_points(e.get("d", ""))[-1][1][1]
            for e in root.iter(f"{SVG_NS}path")
            if "life" in _classes(e)
        ),
    )
    for text in root.iter(f"{SVG_NS}text"):
        if text.get("class") not in {"msg", "guard"}:
            continue
        left, upper, right, lower = text_box(text, styles)
        if lower < top or upper > bottom:
            continue
        assert not [x for x in lanes if left < x < right], f"'{text.text}' sits over a lifeline"


# --- Scenario: Each diagram stays within its complexity budget ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_7_within_budget(path: Path) -> None:
    root = _load(path)
    assert len(groups(root, "node")) <= 9, "at most 9 nodes"
    assert len(connectors(root)) <= 12, "at most 12 connectors"
    accents = [
        e
        for e in root.iter()
        if any("accent" in c for c in _classes(e)) and "sample" not in _classes(e)
    ]
    accents = [e for e in accents if e.tag != f"{SVG_NS}polygon"]
    assert 1 <= len(accents) <= 2, f"{path.name}: 1 or 2 accent elements, found {len(accents)}"
    callouts = {e.get("y") for e in root.iter(f"{SVG_NS}text") if e.get("class") == "callout"}
    assert len(callouts) <= 2, "at most 2 callout lines"
    if path.name == SEQUENCE:
        assert len([e for e in root.iter(f"{SVG_NS}path") if "life" in _classes(e)]) <= 5
        assert len(connectors(root)) <= 12, "at most 12 messages"
        assert len([e for e in root.iter(f"{SVG_NS}rect") if "frame" in _classes(e)]) == 1
