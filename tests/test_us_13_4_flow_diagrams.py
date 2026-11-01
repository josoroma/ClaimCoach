"""US-13.4 App Flow Diagrams for Stakeholders and Users.

Scenarios: the stakeholder diagram shows the PHI boundary; the user diagram follows a case from
upload to outcome; the developer diagram follows one request; the diagrams are self-contained and
readable in light and dark themes. Positions, arrows, and colors are read from each SVG, so a box
moved across the Mac's edge, a PHI arrow drawn to the chat agent, a model shown on the wrong step,
or a class left without dark colors fails the check.
Rules: BR-2, BR-3, BR-4, PRD §7.2, §10.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from fastapi.routing import APIRoute

from claimcoach.api.routes import router as gateway
from claimcoach.events import CaseProgressEvent
from claimcoach.worker import case_routes
from claimcoach.worker.config import WorkerConfig
from tests.conftest import REPO_ROOT
from tests.doc_checks import section
from tests.svg_checks import SVG_NS, self_contained_svg
from tests.test_us_13_2_dev_guide import GUIDE, REGISTRY

ASSETS = REPO_ROOT / "docs" / "assets"
STAKEHOLDER = ASSETS / "flow-stakeholder.svg"
USER = ASSETS / "flow-user.svg"
REQUEST = ASSETS / "flow-request.svg"
DIAGRAMS = sorted(ASSETS.glob("*.svg"))
Box = tuple[float, float, float, float]
Point = tuple[float, float]


def _items(root: ET.Element) -> list[tuple[str, Point]]:
    """Every text of the diagram with where it is drawn, in drawing order."""
    return [
        ((element.text or "").strip(), (float(element.get("x", "0")), float(element.get("y", "0"))))
        for element in root.iter(f"{SVG_NS}text")
    ]


def _texts(root: ET.Element) -> dict[str, Point]:
    """Every text of the diagram → where it is drawn; a label drawn twice is refused."""
    found: dict[str, Point] = {}
    for label, point in _items(root):
        assert label not in found, f"'{label}' is drawn twice"
        found[label] = point
    return found


def _rects(root: ET.Element, *classes: str) -> list[Box]:
    """The ``x, y, right, bottom`` of every ``rect`` whose class is one of ``classes``."""
    boxes = []
    for element in root.iter(f"{SVG_NS}rect"):
        if element.get("class") in classes:
            x, y = float(element.get("x", "0")), float(element.get("y", "0"))
            right = x + float(element.get("width", "0"))
            boxes.append((x, y, right, y + float(element.get("height", "0"))))
    return boxes


def _inside(point: Point, box: Box) -> bool:
    x, y = point
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _box_of(point: Point, boxes: list[Box]) -> Box:
    """The smallest of ``boxes`` that holds ``point``."""
    holding = [box for box in boxes if _inside(point, box)]
    assert holding, f"nothing drawn around {point}"
    return min(holding, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))


def _ends(d: str) -> tuple[Point, Point]:
    """The first and last points of a path made of absolute ``M``, ``L``, ``H``, and ``V``."""
    x = y = 0.0
    points = []
    for command, args in re.findall(r"([MLHV])([-\d.\s]+)", d):
        values = [float(value) for value in args.split()]
        if command in "ML":
            x, y = values[0], values[1]
        elif command == "H":
            x = values[0]
        else:
            y = values[0]
        points.append((x, y))
    return points[0], points[-1]


def _models() -> dict[str, str]:
    roles = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["roles"]
    return {role: spec["model_dir"] for role, spec in roles.items()}


# --- Scenario: The stakeholder diagram shows the PHI boundary ---
def test_us_13_4_stakeholder_diagram_shows_boundary() -> None:
    root = self_contained_svg(STAKEHOLDER)
    texts = _texts(root)
    (mac,) = _rects(root, "zone")
    for part in (
        "ClaimCoach pane",
        "plugin_api.py",
        "Worker",
        "Local models",
        "Global corpus",
        "User corpus",
        "Agent tools",
    ):
        assert part in texts, f"{part} is not drawn"
        assert _inside(texts[part], mac), f"{part} must be inside the Mac"
    for outside in ("Hermes chat agent", "Payers", "Model weights"):
        assert outside in texts, f"{outside} is not drawn"
        assert not _inside(texts[outside], mac), f"{outside} must be outside the Mac"
    cards = _rects(root, "card", "key", "ext")
    tools = _box_of(texts["Agent tools"], cards)
    agent = _box_of(texts["Hermes chat agent"], cards)
    into_agent = []
    for path in root.iter(f"{SVG_NS}path"):
        if not path.get("marker-end"):
            continue
        start, end = _ends(path.get("d", ""))
        if _inside(end, (agent[0] - 6, agent[1], agent[2], agent[3])):
            into_agent.append((path.get("class"), start))
    assert into_agent, "an arrow reaches the chat agent"
    for css, start in into_agent:
        assert css == "leave", "only a no-PHI, boundary-crossing arrow reaches the chat agent"
        assert _inside(start, (tools[0], tools[1], tools[2] + 2, tools[3])), "from the tools"
    for label in ("case IDs, codes, payer", "names, redacted summaries"):
        x, _ = texts[label]
        assert tools[2] < x < agent[0], f"'{label}' labels the tools-to-agent arrow"


# --- Scenario: The user diagram follows a case from upload to outcome ---
def test_us_13_4_user_diagram_follows_case() -> None:
    root = self_contained_svg(USER)
    items = _items(root)
    texts = {label: point for label, point in items if label != "You"}  # two steps are yours
    cards = _rects(root, "card", "you", "mgr")
    models = _models()
    steps = [
        ("Add documents", []),
        ("Extract", ["extraction"]),
        ("Confirm", []),
        ("Diagnose", ["classification", "explanation"]),
        ("Draft", ["drafting"]),
        ("Edit and export", []),
        ("Record the outcome", []),
    ]
    for number, (title, roles) in enumerate(steps, 1):
        assert title in texts, f"step {title} is not drawn"
        card = _box_of(texts[title], cards)
        assert _inside(texts[str(number)], card), f"{title} is step {number}"
        inside = [label for label, point in items if _inside(point, card)]
        chip = " · ".join(inside)
        for role in roles:
            assert any(models[role].startswith(token) for token in re.split(r" · |\s", chip)), (
                f"{title}'s card names the {role} model"
            )
    named = re.findall(r"\b[A-Z][\w.]*(?:-[\w.]+)*-\d+B\b", " ".join(texts))
    assert named, "the diagram names its models"
    for model in named:
        assert any(folder.startswith(model) for folder in models.values()), f"{model}?"
    assert models["transcription"].startswith("Voxtral-Small-24B")
    assert "Transcribed after hours · Voxtral-Small-24B" in texts
    assert "yourself. ClaimCoach never sends." in texts


# --- Scenario: The developer diagram follows one request ---
def test_us_13_4_request_diagram_follows_request() -> None:
    root = self_contained_svg(REQUEST)
    texts = _texts(root)
    gateway_paths = {route.path for route in gateway.routes if isinstance(route, APIRoute)}
    worker_paths = {
        route.path
        for router in (case_routes.router, case_routes.jobs_router)
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    steps = {
        "process": ("POST /cases/{case_id}/process", gateway_paths),
        "extract": ("POST /cases/{case_id}/extract", worker_paths),
        "events": ("GET /jobs/{job_id}/events", worker_paths),
        "case": ("GET /cases/{case_id} → Case", gateway_paths),
    }
    for label, paths in steps.values():
        assert label in texts, f"{label} is not drawn"
        assert label.split()[1] in paths, f"{label} is not a route"
    event = f"plugin.claimcoach.{CaseProgressEvent.EVENT}"
    assert event in texts
    port = yaml.safe_load(REGISTRY.read_text())["roles"]["extraction"]["port"]
    assert f"extraction · :{port}" in texts
    assert f"127.0.0.1:{WorkerConfig.model_fields['port'].default}" in texts
    order = [texts[label][1] for label in (steps["process"][0], steps["extract"][0])]
    order += [texts[label][1] for label in ("JobStarted {job_id, kind}", steps["events"][0])]
    order += [texts[event][1], texts[steps["case"][0]][1]]
    assert order == sorted(order), "the steps are drawn in order"
    (loop,) = _rects(root, "loop")
    for label in (steps["events"][0], "start on first use", "put_case_item + audit_log", event):
        assert _inside(texts[label], loop), f"{label} repeats while the job runs"
    for label in ("JobStarted {job_id, kind}", steps["case"][0]):
        assert not _inside(texts[label], loop), f"{label} happens once"


def _css(style: str) -> tuple[dict[str, str], dict[str, str]]:
    """The light and dark rules of a diagram's style: class → declarations."""
    light, _, dark = style.partition("@media (prefers-color-scheme: dark)")

    def rules(text: str) -> dict[str, str]:
        found: dict[str, str] = {}
        for selectors, body in re.findall(r"([.\w,\s-]+)\{([^{}]*)\}", text):
            for selector in selectors.split(","):
                found[selector.strip().lstrip(".")] = body
        return found

    return rules(light), rules(dark)


# --- Scenario: The diagrams are self-contained and readable in light and dark themes ---
def test_us_13_4_diagrams_self_contained() -> None:
    assert {path.name for path in DIAGRAMS} >= {
        "flow-request.svg",
        "flow-stakeholder.svg",
        "flow-user.svg",
    }
    flows = section(GUIDE.read_text(encoding="utf-8"), "App flows")
    shown = re.sub(r"<!--.*?-->", "", flows, flags=re.S)
    for path in DIAGRAMS:
        _check_diagram(path)
        assert re.search(rf"!\[[^\]]+\]\(docs/assets/{re.escape(path.name)}\)", shown), (
            f"{path.name} is not shown under App flows"
        )


def _check_diagram(path: Path) -> None:
    root = self_contained_svg(path)
    x, y, width, height = (float(value) for value in (root.get("viewBox") or "").split())
    drawn = [child for child in root if child.tag.removeprefix(SVG_NS) not in _NOT_DRAWN]
    assert drawn[0].get("class") == "bg", f"{path.name}: the background is drawn first"
    assert _rects(root, "bg") == [(x, y, x + width, y + height)], f"{path.name}: full background"
    style = root.find(f"{SVG_NS}style")
    assert style is not None
    light, dark = _css(style.text or "")
    assert "fill:" in light["bg"], f"{path.name}: light background color"
    assert "fill:" in dark.get("bg", ""), f"{path.name}: dark background color"
    missing = sorted(set(light) - set(dark))
    assert not missing, f"{path.name}: no dark colors for {missing}"


_NOT_DRAWN = {"title", "desc", "style", "defs"}


def test_us_13_4_diagram_check_refuses_light_only(tmp_path: Path) -> None:
    body = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><title>x</title>'
        "<style>.bg{{fill:#fff}}.t{{fill:#000}}"
        "@media (prefers-color-scheme: dark){{{dark}}}</style>"
        '<rect class="bg" x="0" y="0" width="10" height="10"/></svg>'
    )
    path = tmp_path / "flow.svg"
    path.write_text(body.format(dark=".bg{fill:#000}"), encoding="utf-8")
    with pytest.raises(AssertionError, match=r"no dark colors for \['t'\]"):
        _check_diagram(path)
    path.write_text(body.format(dark=".bg{fill:#000}.t{fill:#fff}"), encoding="utf-8")
    _check_diagram(path)
    assert _ends("M1 2H5V9") == ((1.0, 2.0), (5.0, 9.0))
    assert _ends("M1 2L3 4") == ((1.0, 2.0), (3.0, 4.0))
