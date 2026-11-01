"""US-13.1 Shared ClaimCoach Logo on the Plugin Pages (the logo file).

Scenario: one logo file is the source of the mark. The pages' scenarios run under ``node --test``
(``plugin/desktop/tests/shared_logo.test.mjs``), which also compares plugin.js's shapes with this
file. The self-contained check lives in ``tests/svg_checks.py``, shared with US-13.4.
Rules: PC-3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import PLUGIN_DIR
from tests.svg_checks import SVG_NS, self_contained_svg

LOGO = PLUGIN_DIR / "assets" / "claimcoach-logo.svg"
_ROOT_ATTRIBUTES = {"viewBox", "width", "height", "role", "aria-labelledby"}


# --- Scenario: One logo file is the source of the mark ---
def test_us_13_1_logo_file_self_contained() -> None:
    root = self_contained_svg(LOGO)
    assert root.get("viewBox") == "0 0 64 64"
    assert set(root.attrib) == _ROOT_ATTRIBUTES, "nothing on the root restyles the mark"
    title = root.find(f"{SVG_NS}title")
    assert title is not None
    assert title.text == "ClaimCoach"
    drawn = [element for element in root.iter() if element is not root and element is not title]
    assert drawn, "the mark draws something"
    for element in drawn:
        tag = element.tag.removeprefix(SVG_NS)
        assert tag in {"rect", "path"}, f"<{tag}>: the mark is plain shapes plugin.js can draw"
        assert len(element) == 0, f"<{tag}> has children plugin.js would not draw"
    assert "'" not in LOGO.read_text(encoding="utf-8"), "double quotes only, as plugin.js reads it"


_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><title>x</title>{}</svg>'


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ('<svg xmlns="http://www.w3.org/2000/svg"><title>x</title></svg>', "no viewBox"),
        ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>', "no title"),
        (_SVG.format("<script>alert(1)</script>"), "<script>"),
        (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 1 1"><title>x</title><rect x:href="a.svg"/></svg>',
            "references another file",
        ),
        (_SVG.format('<rect onclick="x()"/>'), "event handler"),
        (_SVG.format('<rect fill="url( http://a/b )"/>'), "external url"),
        (_SVG.format("<rect fill=\"url('https://a/p.svg#g')\"/>"), "external url"),
        (_SVG.format('<rect fill="URL(HTTPS://A/B)"/>'), "external url"),
        (_SVG.format('<rect fill="url(//a/b)"/>'), "external url"),
        (_SVG.format("<rect style=\"fill:url('https://a/b')\"/>"), "external url"),
        (_SVG.format("<style>rect{fill:url(https://a/b)}</style>"), "external url"),
        (_SVG.format("<style>@import 'x.css';</style>"), "@import"),
        ('<?xml-stylesheet href="https://a/b.css"?>' + _SVG.format(""), "xml-stylesheet"),
        ('<!DOCTYPE svg [<!ENTITY e "x">]>' + _SVG.format(""), "DOCTYPE"),
        (
            _SVG.format(
                '<path d="M0 0"><h:script xmlns:h="http://www.w3.org/1999/xhtml">x</h:script></path>'
            ),
            "outside SVG",
        ),
        ("<html/>", "not an SVG"),
    ],
)
def test_us_13_1_check_refuses_unsafe_svg(tmp_path: Path, body: str, problem: str) -> None:
    path = tmp_path / "bad.svg"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(AssertionError, match=problem):
        self_contained_svg(path)


def test_us_13_1_check_allows_local_references(tmp_path: Path) -> None:
    path = tmp_path / "ok.svg"
    path.write_text(_SVG.format('<path marker-end="url(#a)"/><rect fill="url( \'#g\')"/>'))
    assert self_contained_svg(path).get("viewBox") == "0 0 1 1"
