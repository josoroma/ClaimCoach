"""US-13.4 App Flow Diagrams for Stakeholders and Users.

Scenarios: the stakeholder diagram shows the PHI boundary; the user diagram follows a case from
upload to outcome; the developer diagram follows one extraction; the diagrams are self-contained and
shown in README-DEV.md. Since US-13.7 the diagrams are diagram-design drawings on a transparent
canvas, and since US-13.8 they take the theme's colors, dark by default and light on a light page
(their own checks are in ``test_us_13_7_*`` and ``test_us_13_8_*``). Nodes are ``<g class="node">``
groups, read by their name; positions and arrows come from the SVG, so a box moved across the
Mac's edge, a PHI arrow drawn to the chat agent, a model shown on the wrong step, or a message drawn
between the wrong lifelines fails here.
Rules: BR-2, BR-3, BR-4, PRD §7.2, §10.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from itertools import pairwise

import yaml
from fastapi.routing import APIRoute

from claimcoach.api.routes import router as gateway
from claimcoach.cases.extraction import JobStarted
from claimcoach.corpus.store import CorpusStore
from claimcoach.events import CaseProgressEvent
from claimcoach.worker import case_routes
from claimcoach.worker.config import WorkerConfig
from tests.conftest import REPO_ROOT
from tests.doc_checks import section
from tests.svg_checks import SVG_NS, self_contained_svg
from tests.svg_layout import Box, container, groups, inside, own_texts, path_points, rect_box
from tests.test_us_13_2_dev_guide import GUIDE, REGISTRY

ASSETS = REPO_ROOT / "docs" / "assets"
STAKEHOLDER = ASSETS / "flow-stakeholder.svg"
USER = ASSETS / "flow-user.svg"
REQUEST = ASSETS / "flow-request.svg"
DIAGRAMS = sorted(ASSETS.glob("*.svg"))
Point = tuple[float, float]


def _classes(element: ET.Element) -> set[str]:
    return set((element.get("class") or "").split())


def _nodes(root: ET.Element) -> dict[str, tuple[Box, list[str]]]:
    """Each node by its name: its box and every text it holds (tag, name, sublabel)."""
    found = {}
    for node in groups(root, "node"):
        names = [text.text or "" for text in own_texts(node) if text.get("class") == "name"]
        assert len(names) == 1, "a node has one name"
        found[names[0]] = (
            rect_box(container(node)),
            [text.text or "" for text in node.iter(f"{SVG_NS}text")],
        )
    return found


def _texts(root: ET.Element) -> dict[str, Point]:
    """Every text that is not inside a node → where it is drawn; one drawn twice is refused."""
    in_nodes = {id(t) for node in groups(root, "node") for t in node.iter(f"{SVG_NS}text")}
    found: dict[str, Point] = {}
    for text in root.iter(f"{SVG_NS}text"):
        if id(text) in in_nodes:
            continue
        label = text.text or ""
        assert label not in found, f"'{label}' is drawn twice"
        found[label] = (float(text.get("x", "0")), float(text.get("y", "0")))
    return found


def _rect(root: ET.Element, css: str) -> Box:
    (box,) = [rect_box(r) for r in root.iter(f"{SVG_NS}rect") if css in _classes(r)]
    return box


def _at(point: Point, box: Box) -> bool:
    x, y = point
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _arrows(root: ET.Element) -> list[tuple[set[str], str, list[Point]]]:
    """Every arrow drawn (legend samples aside): its classes, its marker, and its points."""
    return [
        (_classes(path), path.get("marker-end", ""), [p for _, p in path_points(path.get("d", ""))])
        for path in root.iter(f"{SVG_NS}path")
        if _classes(path) & {"arrow", "arrow-accent"} and "sample" not in _classes(path)
    ]


def _flows(root: ET.Element) -> dict[tuple[str, str], set[str]]:
    """Each arrow from one node to another → its classes; an arrow that does not join two nodes
    is refused."""
    nodes = _nodes(root)
    found = {}
    for classes, _, points in _arrows(root):
        ends = [
            [name for name, (box, _) in nodes.items() if _at(point, box)]
            for point in (points[0], points[-1])
        ]
        assert all(len(end) == 1 for end in ends), f"an arrow at {points[0]} joins two nodes"
        found[(ends[0][0], ends[1][0])] = classes
    return found


def _models() -> dict[str, str]:
    roles = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["roles"]
    return {role: spec["model_dir"] for role, spec in roles.items()}


def _named(texts: list[str]) -> list[str]:
    """The model names (``Qwen3-VL-8B``, ``Ternary-Bonsai-2-27B``) in some texts."""
    return re.findall(r"\b[A-Z][\w.]*(?:-[\w.]+)*-\d+B\b", " ".join(texts))


# --- Scenario: The stakeholder diagram shows the PHI boundary ---
def test_us_13_4_stakeholder_diagram_shows_boundary() -> None:
    root = self_contained_svg(STAKEHOLDER)
    nodes = _nodes(root)
    texts = _texts(root)
    mac = _rect(root, "zone-accent")
    for part in (
        "ClaimCoach pane",
        "plugin_api.py",
        "Worker",
        "Local models",
        "PDF or DOCX",
        "Global corpus",
        "User corpus",
        "Agent tools",
    ):
        assert part in nodes, f"{part} is not drawn"
        assert inside(nodes[part][0], mac), f"{part} must be inside the Mac"
    agent, tools = nodes["Hermes chat agent"][0], nodes["Agent tools"][0]
    assert not inside(agent, mac), "the chat agent is outside the Mac"
    assert nodes["Hermes chat agent"][1][2] == "IDs · codes · payer names", "what it may see"
    assert inside(agent, _rect(root, "zone")), "it sits in the outside band"
    assert nodes["Local models"][1][2] == f"{len(_models())} roles · loopback"
    assert nodes["Worker"][1][2] == f"127.0.0.1:{WorkerConfig.model_fields['port'].default}"
    for callout in (
        "Model weights arrive only after you confirm a download.",
        "Nothing is sent to a payer: you file the export yourself.",
    ):
        assert callout in texts, f"'{callout}' is not drawn"
        assert not _at(texts[callout], mac), f"'{callout}' belongs outside the Mac"
    phi, no_phi, redacted = {"arrow"}, {"arrow", "nophi"}, {"arrow-accent", "nophi"}
    assert _flows(root) == {
        ("ClaimCoach pane", "plugin_api.py"): phi,
        ("plugin_api.py", "Worker"): phi,
        ("Worker", "Local models"): phi,
        ("ClaimCoach pane", "PDF or DOCX"): phi,
        ("Worker", "Global corpus"): no_phi,
        ("Worker", "User corpus"): phi,
        ("Worker", "Agent tools"): no_phi,
        ("Agent tools", "Hermes chat agent"): redacted,
    }, "case content stays on the Mac; only redacted results reach the chat agent"
    chip_x, chip_y = texts["REDACTED ONLY"]
    assert tools[3] < chip_y < agent[1], "the crossing arrow is labeled between the two"
    assert chip_x > (tools[0] + tools[2]) / 2


# --- Scenario: The user diagram follows a case from upload to outcome ---
def test_us_13_4_user_diagram_follows_case() -> None:
    root = self_contained_svg(USER)
    nodes = _nodes(root)
    models = _models()
    steps = [
        ("Add documents", [], False),
        ("Extract", ["extraction"], False),
        ("Confirm", [], True),
        ("Diagnose", ["classification", "explanation"], False),
        ("Draft", ["drafting"], False),
        ("Edit and export", [], True),
        ("Record the outcome", [], True),
    ]
    for number, (title, roles, yours) in enumerate(steps, 1):
        assert title in nodes, f"step {title} is not drawn"
        tag, _, sub = nodes[title][1]
        assert tag == f"STEP {number}" + (" · YOU" if yours else ""), f"{title} is step {number}"
        named = _named([sub])
        assert len(named) == len(roles), f"{title} names the models of its own roles only"
        for role, model in zip(roles, named, strict=True):
            assert models[role].startswith(model), f"{title} names the {role} model"
    assert models["transcription"].startswith(nodes["Payer call"][1][2])
    assert "never sent" in nodes["Edit and export"][1][2]
    edit = [
        n for n in groups(root, "node") if any(t.text == "Edit and export" for t in own_texts(n))
    ]
    assert "node-accent" in _classes(container(edit[0])), "human review is the focal step"
    flows = _flows(root)
    for (first, _, _), (second, _, _) in pairwise(steps):
        assert (first, second) in flows, f"no arrow from {first} to {second}"
    assert flows.pop(("Record the outcome", "Manager dashboard")) == {"arrow", "nophi"}
    assert flows.pop(("Payer call", "Add documents")) == {"arrow"}
    assert len(flows) == len(steps) - 1, "every other arrow joins one step to the next"


# --- Scenario: The developer diagram follows one extraction ---
def _messages(root: ET.Element) -> list[tuple[str, str, str, str]]:
    """Each message, top to bottom: its label, the lifelines its arrow (drawn 8px under the label)
    joins, and what it is: a call, a return, an event (dashed, open head), or the sealed write."""
    heads = {(box[0] + box[2]) / 2: name for name, (box, _) in _nodes(root).items()}
    arrows = {points[0][1]: (classes, marker, points) for classes, marker, points in _arrows(root)}
    found = []
    for text in root.iter(f"{SVG_NS}text"):
        if text.get("class") != "msg":
            continue
        x, y = float(text.get("x", "0")), float(text.get("y", "0"))
        classes, marker, points = arrows.pop(y + 8)
        (x0, _), (x1, _) = points[0], points[-1]
        assert min(x0, x1) < x < max(x0, x1), f"'{text.text}' is not over its arrow"
        kind = (
            "sealed"
            if "arrow-accent" in classes
            else "event"
            if marker.endswith("-head-open)")
            else "return"
            if "return" in classes
            else "call"
        )
        found.append((y, (text.text or "", heads[x0], heads[x1], kind)))
    assert arrows == {}, "every arrow carries a message"
    return [message for _, message in sorted(found)]


def test_us_13_4_request_diagram_follows_request() -> None:
    root = self_contained_svg(REQUEST)
    nodes = _nodes(root)
    texts = _texts(root)
    gateway_paths = {route.path for route in gateway.routes if isinstance(route, APIRoute)}
    worker_paths = {
        route.path
        for router in (case_routes.router, case_routes.jobs_router)
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    process, extract = "POST /cases/{case_id}/process", "POST /cases/{case_id}/extract"
    events, case = "GET /jobs/{job_id}/events", "GET /cases/{case_id}"
    for label, paths in ((process, gateway_paths), (extract, worker_paths)):
        assert label.split()[1] in paths, f"{label} is not a route"
    for label, paths in ((events, worker_paths), (case, gateway_paths)):
        assert label.split()[1] in paths, f"{label} is not a route"
    assert {"job_id", "kind"} <= set(JobStarted.model_fields)
    assert callable(CorpusStore.put_case_item)
    event = f"plugin.claimcoach.{CaseProgressEvent.EVENT}"
    port = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["roles"]["extraction"]["port"]
    assert nodes["Model server"][1][1] == f"extraction · :{port}"
    assert nodes["Worker"][1][1] == f"127.0.0.1:{WorkerConfig.model_fields['port'].default}"
    pane, api, worker = "Pane", "plugin_api.py", "Worker"
    assert _messages(root) == [
        (process, pane, api, "call"),
        (extract, api, worker, "call"),
        ("JobStarted {job_id, kind}", worker, api, "return"),
        ("JobStarted", api, pane, "return"),
        ("POST /v1/chat/completions", worker, "Model server", "call"),
        ("JSON fields, read as data", "Model server", worker, "return"),
        ("put_case_item + audit_log", worker, "User corpus", "sealed"),
        (events, api, worker, "call"),
        ("events after n", worker, api, "return"),
        (event, api, pane, "event"),
        (case, pane, api, "call"),
        ("Case", api, pane, "return"),
    ]
    for note, message in (
        ("per-launch bearer token", extract),
        ("first use · memory guard", "POST /v1/chat/completions"),
        ("proxied to the worker", case),
    ):
        assert texts[note][0] == texts[message][0], f"'{note}' sits under '{message}'"
        assert 0 < texts[note][1] - (texts[message][1] + 8) <= 24, f"'{note}' annotates it"
    loop = _rect(root, "frame")
    for label in ("LOOP", "[until the job ends]", events, "events after n", event):
        assert _at(texts[label], loop), f"{label} repeats until the job ends"
    # A message repeats when its arrow (8px under its label) is within the loop's height.
    repeats = [label for label, *_ in _messages(root) if loop[1] < texts[label][1] + 8 < loop[3]]
    assert repeats == [events, "events after n", event], "only the polling repeats"


# --- Scenario: The diagrams are self-contained and shown in README-DEV.md ---
def test_us_13_4_diagrams_self_contained() -> None:
    assert [path.name for path in DIAGRAMS] == [
        "flow-request.svg",
        "flow-stakeholder.svg",
        "flow-user.svg",
    ]
    flows = section(GUIDE.read_text(encoding="utf-8"), "App flows")
    shown = re.sub(r"<!--.*?-->", "", flows, flags=re.S)
    for path in DIAGRAMS:
        root = self_contained_svg(path)
        style = root.find(f"{SVG_NS}style")
        assert style is not None
        assert "@media (prefers-color-scheme: light)" in (style.text or ""), f"{path.name}: light"
        assert re.search(rf"!\[[^\]]+\]\(docs/assets/{re.escape(path.name)}\)", shown), (
            f"{path.name} is not shown under App flows"
        )
