"""US-13.8 Diagram Theme from the Design Tokens.

Scenarios: colors come from the theme tokens; dark is the default; light is handled; text and
marks stay readable in both themes. ``docs/assets/theme.css`` is the theme as given (``:root``
light, ``.dark`` dark). Each diagram copies the tokens it uses: ``:root`` light, ``.dark`` dark (the
root carries ``class="dark"``), and the light values again in its one ``@media
(prefers-color-scheme: light)`` block, for a light page.

Contrast is WCAG (diagram-design ``style-guide.md``): text 4.5:1, essential lines 3:1. Every color
is what a browser paints: the computed style (rules by specificity, inherited fill and stroke,
opacity down the tree), composited in sRGB space over what the text actually sits on (its node or
chip, the loop's wash, or the page, which stands in for the transparent canvas). Node hairlines,
chip and tag outlines, and the legend rule are decorative and have no minimum.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.svg_checks import SVG_NS
from tests.svg_layout import (
    RGB,
    TOKEN_SELECTORS,
    classes,
    computed,
    contrast,
    contrast_of,
    css_rules,
    luminance,
    media_rules,
    oklch,
    opaque,
    over,
    rect_box,
    style_of,
)
from tests.test_us_13_6_text_fit import DIAGRAMS

THEME = REPO_ROOT / "docs" / "assets" / "theme.css"
LIGHT_QUERY = "(prefers-color-scheme: light)"
COLOR_PROPERTIES = ("fill", "stroke", "color", "stop-color", "flood-color", "lighting-color")
DECORATIVE = {"rect.node", "rect.chip", "rect.tag", "rect.tab", "path.rule"}
"""Hairlines that carry no meaning of their own (diagram-design: decorative, no minimum)."""
_VAR = re.compile(r"var\(--([\w-]+)\)")


def _load(path: Path) -> ET.Element:
    return ET.parse(path).getroot()  # noqa: S314 - ours, checked self-contained by US-13.4


def theme(selector: str) -> dict[str, str]:
    """A block of ``theme.css``: token name → value."""
    text = THEME.read_text(encoding="utf-8")
    body = re.search(re.escape(selector) + r"\s*\{(.*?)\}", text, re.S)
    assert body, f"theme.css has no {selector} block"
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", body.group(1)))


def tokens(rules: list[tuple[str, dict[str, str]]], selector: str) -> dict[str, str]:
    """The ``--token`` declarations of ``selector``."""
    found = [body for name, body in rules if name == selector]
    assert len(found) == 1, f"one {selector} rule"
    return {name[2:]: value for name, value in found[0].items() if name.startswith("--")}


def _token(value: str) -> str:
    match = _VAR.fullmatch(value)
    assert match, f"{value} is not a theme token"
    return match.group(1)


def color_problems(root: ET.Element) -> list[str]:
    """Each color declaration, outside the token blocks, that is not a theme token or ``none``,
    and each element attribute that sets a color."""
    problems = [
        f"{selector} {prop}: {value}"
        for selector, body in css_rules(style_of(root))
        if selector not in TOKEN_SELECTORS
        for prop, value in body.items()
        if prop in COLOR_PROPERTIES and value != "none" and not _VAR.fullmatch(value)
    ]
    problems += [
        f"<{element.tag.removeprefix(SVG_NS)}> sets {attribute}"
        for element in root.iter()
        for attribute in (*COLOR_PROPERTIES, "style")
        if element.get(attribute) is not None
    ]
    return problems


def palette(root: ET.Element, mode: str) -> dict[str, str]:
    """The token values a diagram uses in ``mode`` (``light`` or ``dark``)."""
    rules = css_rules(style_of(root))
    return tokens(rules, ".dark") if mode == "dark" else tokens(rules, ":root")


def _paint(style: dict[str, str], prop: str, colors: dict[str, str], under: RGB) -> RGB | None:
    """``style``'s ``prop`` painted over ``under``, or ``None`` when it paints nothing."""
    value = style.get(prop, "none")
    if value == "none":
        return None
    alpha = float(style.get(f"{prop}-opacity", "1")) * float(style.get("opacity", "1"))
    return over(colors[_token(value)], alpha, under)


def _surface(root: ET.Element, text: ET.Element, colors: dict[str, str]) -> RGB:
    """What ``text`` sits on: the innermost painted container rect of its groups, else the loop's
    wash when it is inside the frame, else the page."""
    page = opaque(colors["background"])
    parents = {child: parent for parent in root.iter() for child in parent}
    node = text
    while node in parents:
        node = parents[node]
        if node.tag == f"{SVG_NS}g" and classes(node) & {"node", "chip", "tag"}:
            rect = node.find(f"{SVG_NS}rect")
            assert rect is not None
            painted = _paint(computed(root, rect), "fill", colors, page)
            if painted is not None:
                return painted
    x, y = float(text.get("x", "0")), float(text.get("y", "0"))
    for frame in root.iter(f"{SVG_NS}rect"):
        if "frame" in classes(frame):
            left, top, right, bottom = rect_box(frame)
            if left <= x <= right and top <= y <= bottom:
                wash = _paint(computed(root, frame), "fill", colors, page)
                assert wash is not None
                return wash
    return page


def text_problems(root: ET.Element, mode: str) -> list[str]:
    """Each text under 4.5:1 against what it sits on, or drawn with a stroke."""
    colors = palette(root, mode)
    problems = []
    for text in root.iter(f"{SVG_NS}text"):
        style = computed(root, text)
        if style.get("stroke", "none") != "none":
            problems.append(f"{mode}: '{text.text}' is stroked with {style['stroke']}")
        under = _surface(root, text, colors)
        fore = _paint(style, "fill", colors, under)
        assert fore is not None, f"'{text.text}' has no fill"
        ratio = contrast_of(fore, under)
        if ratio < 4.5:
            problems.append(f"{mode}: '{text.text}' is {ratio:.2f}:1")
    return problems


def mark_problems(root: ET.Element, mode: str) -> list[str]:
    """Each essential line or arrowhead under 3:1 on the page, or on the loop's wash."""
    colors = palette(root, mode)
    page = opaque(colors["background"])
    surfaces = [("page", page)]
    for frame in root.iter(f"{SVG_NS}rect"):
        if "frame" in classes(frame):
            wash = _paint(computed(root, frame), "fill", colors, page)
            assert wash is not None
            surfaces.append(("wash", wash))
    problems = []
    for selector, body in css_rules(style_of(root)):
        if selector in TOKEN_SELECTORS or selector in DECORATIVE or not selector[:1].isalpha():
            continue
        if selector == "text":
            continue
        for prop in ("stroke", "fill"):
            value = body.get(prop, "none")
            if value == "none" or (prop == "fill" and selector.startswith("rect.")):
                continue
            for name, under in surfaces:
                ratio = contrast_of(over(colors[_token(value)], 1.0, under), under)
                if ratio < 3:
                    problems.append(f"{mode}: {selector} {prop} is {ratio:.2f}:1 on the {name}")
    return problems


# --- Scenario: Colors come from the theme tokens ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_8_colors_from_tokens(path: Path) -> None:
    root = _load(path)
    rules = css_rules(style_of(root))
    light, dark = tokens(rules, ":root"), tokens(rules, ".dark")
    assert set(light) == set(dark), "every token has a light and a dark value"
    for name, value in light.items():
        assert value == theme(":root")[name], f"--{name} (light) differs from theme.css"
        assert dark[name] == theme(".dark")[name], f"--{name} (dark) differs from theme.css"
    assert color_problems(root) == []
    used = {
        _token(value)
        for selector, body in rules
        if selector not in TOKEN_SELECTORS
        for prop, value in body.items()
        if prop in COLOR_PROPERTIES and value != "none"
    }
    assert used <= set(light), f"tokens used but not defined: {sorted(used - set(light))}"


def test_us_13_8_literal_colors_are_refused() -> None:
    root = ET.fromstring(  # noqa: S314 - a literal
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><style>'
        ":root{--card:oklch(1 0 0)}.dark{--card:oklch(0.205 0 0)}"
        "text{fill:white}rect{stroke:oklch(0.5 0 0)}.dark .rule{stroke:#fff}.ok{fill:var(--card)}"
        '</style><rect fill="red"/></svg>'
    )
    assert color_problems(root) == [
        "text fill: white",
        "rect stroke: oklch(0.5 0 0)",
        ".dark .rule stroke: #fff",
        "<rect> sets fill",
    ]


# --- Scenario: Dark is the default ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_8_dark_by_default(path: Path) -> None:
    root = _load(path)
    assert "dark" in classes(root), "the diagram is dark for now"
    rules = css_rules(style_of(root))
    assert [name for name, _ in rules][:2] == [":root", ".dark"], "dark overrides the light root"


# --- Scenario: Light is handled ---
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_8_light_handled(path: Path) -> None:
    root = _load(path)
    style = style_of(root)
    assert re.findall(r"@media[^{]*", style) == [f"@media {LIGHT_QUERY}"], "one @media: light"
    override = tokens(media_rules(style, LIGHT_QUERY), ":root.dark")
    rules = css_rules(style)
    assert override == tokens(rules, ":root"), "a light page gets the theme's light values"
    assert set(override) == set(tokens(rules, ".dark"))


# --- Scenario: Text and marks stay readable in both themes ---
@pytest.mark.parametrize("mode", ["dark", "light"])
@pytest.mark.parametrize("path", DIAGRAMS, ids=[path.name for path in DIAGRAMS])
def test_us_13_8_contrast_in_both_themes(path: Path, mode: str) -> None:
    root = _load(path)
    assert text_problems(root, mode) == []
    assert mark_problems(root, mode) == []


_TOKENS = (
    ":root{--background:oklch(1 0 0);--foreground:oklch(0.145 0 0);--card:oklch(1 0 0);"
    "--secondary:oklch(0.97 0 0);--border:oklch(0.922 0 0);--ring:oklch(0.708 0 0)}"
    ".dark{--background:oklch(0.145 0 0);--foreground:oklch(0.985 0 0);--card:oklch(0.205 0 0);"
    "--secondary:oklch(0.269 0 0);--border:oklch(1 0 0 / 10%);--ring:oklch(0.556 0 0)}"
)


def _svg(rules: str, body: str) -> ET.Element:
    return ET.fromstring(  # noqa: S314 - a literal
        f'<svg xmlns="http://www.w3.org/2000/svg" class="dark" viewBox="0 0 100 100">'
        f"<style>{_TOKENS}{rules}</style>{body}</svg>"
    )


_CHIP = (
    '<g class="chip"><rect class="chip" x="0" y="0" width="60" height="16"/>'
    '<text class="label" x="4" y="11">OK</text></g>'
)


@pytest.mark.parametrize(
    ("rules", "problem"),
    [
        (
            ".chip{fill:var(--secondary);stroke:var(--border)}.label{fill:var(--foreground)}",
            "stroked",
        ),
        ("rect.chip{fill:var(--foreground)}.label{fill:var(--foreground)}", "'OK' is 1.00:1"),
        (
            "rect.chip{fill:var(--secondary)}.label{fill:var(--foreground);fill-opacity:0.3}",
            "'OK' is",
        ),
    ],
    ids=["group-stroke-inherited", "container-fill-matches-text", "faded-text"],
)
def test_us_13_8_what_is_painted_is_measured(rules: str, problem: str) -> None:
    root = _svg(rules, _CHIP)
    found = text_problems(root, "dark") + text_problems(root, "light")
    assert [p for p in found if problem in p], found


def test_us_13_8_wash_and_lines_are_measured() -> None:
    root = _svg(
        "rect.frame{fill:var(--foreground);fill-opacity:0.9;stroke:var(--ring)}"
        "path.life{stroke:var(--ring)}.guard{fill:var(--foreground)}",
        '<rect class="frame" x="0" y="0" width="100" height="100"/>'
        '<text class="guard" x="10" y="20">[while]</text><path class="life" d="M50 0V100"/>',
    )
    assert [p for p in text_problems(root, "light") if "'[while]'" in p]
    assert "light: path.life stroke is 2.59:1 on the page" in mark_problems(root, "light")


def test_us_13_8_contrast_math() -> None:
    *gray, _ = oklch("oklch(0.556 0 0)")
    assert luminance((gray[0], gray[1], gray[2])) == pytest.approx(0.17188, abs=1e-4)  # #737373
    assert contrast("oklch(0.556 0 0)", "oklch(1 0 0)") == pytest.approx(4.73, abs=0.01)
    assert contrast("oklch(1 0 0)", "oklch(0 0 0)") == pytest.approx(21, rel=0.01)
    # A translucent white over black is blended in sRGB space before measuring.
    assert 1 < contrast("oklch(1 0 0 / 10%)", "oklch(0 0 0)") < 2
    with pytest.raises(AssertionError, match="translucent"):
        contrast("oklch(1 0 0)", "oklch(1 0 0 / 10%)")
