"""Layout and color helpers for the diagram checks of US-13.6 to US-13.8.

A diagram's ``<style>`` gives each text class its font; ``text_box`` turns a ``<text>`` into the
box it paints, sized with diagram-design's budget (0.60em per character for sans, 0.62em for mono,
0.50em for serif) or the PyMuPDF Helvetica, Courier, or Times metrics, whichever is wider, plus
letter-spacing. Nodes, chips, and tags are ``<g class="node|chip|tag">`` groups whose first
``<rect>`` is the container of the group's own texts. Colors are the theme's oklch tokens, turned
into sRGB to measure WCAG contrast.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import pymupdf

from tests.svg_checks import SVG_NS

Box = tuple[float, float, float, float]
"""``(left, top, right, bottom)``."""
CONTAINERS = ("node", "chip", "tag")
_BUDGET = {"sans": 0.60, "mono": 0.62, "serif": 0.50}
_METRICS = {"sans": ("helv", "hebo"), "mono": ("cour", "cour"), "serif": ("tiit", "tiit")}
_PROPORTIONAL_MARGIN = 1.2
"""Helvetica and Times run narrower than some fallbacks for Geist and Instrument Serif: DejaVu Sans
Bold and DejaVu Serif Italic (Linux's generic ``sans-serif`` and ``serif``) measure up to 19% wider
in Chromium, so proportional fonts get 20%. Mono fallbacks (Menlo, SF Mono, DejaVu Sans Mono,
Courier New) stay within the 0.62em budget."""
_UNMEASURED = ("style", "font-size", "font-weight", "font-family", "transform", "dx", "textLength")


def css_rules(style: str) -> list[tuple[str, dict[str, str]]]:
    """``(selector, declarations)`` for every rule outside an ``@media`` block, in order."""
    outside = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", style)
    rules = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", outside):
        declarations = {
            name.strip(): value.strip()
            for name, _, value in (part.partition(":") for part in body.split(";"))
            if name.strip()
        }
        rules += [(selector.strip(), declarations) for selector in selectors.split(",")]
    return rules


def media_rules(style: str, query: str) -> list[tuple[str, dict[str, str]]]:
    """The rules inside ``@media <query>``."""
    match = re.search(re.escape(f"@media {query}") + r"\s*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", style)
    assert match, f"no @media {query} block"
    return css_rules(match.group(1))


def style_of(root: ET.Element) -> str:
    """The diagram's ``<style>`` text."""
    style = root.find(f"{SVG_NS}style")
    assert style is not None, "no <style>"
    return style.text or ""


@dataclass(frozen=True)
class Font:
    """How a text class is drawn."""

    kind: str
    size: float
    weight: int
    letter_spacing: float
    fill: str


def fonts(root: ET.Element) -> dict[str, Font]:
    """Every text class the style defines, with the ``text`` rule's defaults applied."""
    rules = css_rules(style_of(root))
    default = next((body for selector, body in rules if selector == "text"), {})
    found = {}
    for selector, body in rules:
        if not selector.startswith(".") or "font-size" not in body:
            continue
        merged = {**default, **body}
        family = merged.get("font-family", "")
        kind = "mono" if "Mono" in family or "monospace" in family else "sans"
        if kind == "sans" and re.search(r"(?<!sans-)serif", family):
            kind = "serif"
        size = float(merged["font-size"].removesuffix("px"))
        spacing = merged.get("letter-spacing", "0").removesuffix("em")
        found[selector[1:]] = Font(
            kind=kind,
            size=size,
            weight=int(merged.get("font-weight", "400")),
            letter_spacing=float(spacing),
            fill=merged.get("fill", ""),
        )
    return found


def text_width(text: str, font: Font) -> float:
    """The width ``text`` may take: the diagram-design budget or font metrics, the wider."""
    budget = _BUDGET[font.kind] * font.size * len(text)
    name = _METRICS[font.kind][1 if font.weight >= 600 else 0]
    margin = 1.0 if font.kind == "mono" else _PROPORTIONAL_MARGIN
    measured = pymupdf.get_text_length(text, fontname=name, fontsize=font.size) * margin
    # Browsers add letter-spacing after every glyph, the last one too, and anchor on that advance.
    return max(budget, measured) + len(text) * font.letter_spacing * font.size


def text_box(element: ET.Element, styles: dict[str, Font]) -> Box:
    """The box a ``<text>`` paints: its width from ``text_width``, 0.8em above the baseline and
    0.25em below it."""
    assert len(element) == 0, f"'{element.text}': a <text> with children is not measured"
    unmeasured = [name for name in _UNMEASURED if element.get(name) is not None]
    assert not unmeasured, f"'{element.text}': {unmeasured} change its size unmeasured"
    font = styles[element.get("class", "")]
    width = text_width(element.text or "", font)
    x, y = float(element.get("x", "0")), float(element.get("y", "0"))
    anchor = element.get("text-anchor", "start")
    left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
    return (left, y - 0.8 * font.size, left + width, y + 0.25 * font.size)


def rect_box(element: ET.Element) -> Box:
    """A ``<rect>``'s box."""
    x, y = float(element.get("x", "0")), float(element.get("y", "0"))
    return (x, y, x + float(element.get("width", "0")), y + float(element.get("height", "0")))


def inside(inner: Box, outer: Box, pad_x: float = 0, pad_y: float = 0) -> bool:
    """Whether ``inner`` sits inside ``outer`` with ``pad_x`` left and right and ``pad_y`` above
    and below."""
    return (
        inner[0] >= outer[0] + pad_x
        and inner[1] >= outer[1] + pad_y
        and inner[2] <= outer[2] - pad_x
        and inner[3] <= outer[3] - pad_y
    )


def overlaps(a: Box, b: Box) -> bool:
    """Whether two boxes share any area."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def classes(element: ET.Element) -> set[str]:
    """An element's class tokens."""
    return set((element.get("class") or "").split())


def groups(root: ET.Element, kind: str) -> list[ET.Element]:
    """Every ``<g>`` whose classes include ``kind``."""
    return [g for g in root.iter(f"{SVG_NS}g") if kind in classes(g)]


def container(group: ET.Element) -> ET.Element:
    """A group's own container: its first direct ``<rect>``."""
    rect = group.find(f"{SVG_NS}rect")
    assert rect is not None, f"<g class={group.get('class')}> has no <rect>"
    return rect


def own_texts(group: ET.Element) -> list[ET.Element]:
    """The ``<text>`` children of a group itself (not of its nested groups)."""
    return group.findall(f"{SVG_NS}text")


def free_texts(root: ET.Element) -> list[ET.Element]:
    """Every ``<text>`` that belongs to no node, chip, or tag."""
    held = {
        id(text)
        for kind in CONTAINERS
        for group in groups(root, kind)
        for text in group.iter(f"{SVG_NS}text")
    }
    return [text for text in root.iter(f"{SVG_NS}text") if id(text) not in held]


def view_box(root: ET.Element) -> Box:
    """The ``viewBox`` as a box."""
    x, y, width, height = (float(value) for value in (root.get("viewBox") or "").split())
    return (x, y, x + width, y + height)


def path_points(d: str) -> list[tuple[str, tuple[float, float]]]:
    """``(command, end point)`` for each command of an absolute path (M, L, H, V, A)."""
    points = []
    x = y = 0.0
    for command, args in re.findall(r"([MLHVA])([^MLHVA]*)", d):
        values = [float(value) for value in re.findall(r"-?[\d.]+", args)]
        if command in "ML":
            x, y = values[0], values[1]
        elif command == "H":
            x = values[0]
        elif command == "V":
            y = values[0]
        else:
            x, y = values[5], values[6]
        points.append((command, (x, y)))
    return points


# --- Color --------------------------------------------------------------------------------------


def oklch(value: str) -> tuple[float, float, float, float]:
    """Linear sRGB and alpha of an ``oklch(L C h [/ a%])`` token."""
    match = re.fullmatch(
        r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:/\s*([\d.]+)%)?\s*\)", value
    )
    assert match, f"not an oklch() color: {value}"
    lightness, chroma, hue = (float(part) for part in match.groups()[:3])
    alpha = float(match.group(4)) / 100 if match.group(4) else 1.0
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    red = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    green = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    blue = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    return (_clamp(red), _clamp(green), _clamp(blue), alpha)


def _clamp(channel: float) -> float:
    return min(max(channel, 0.0), 1.0)


def luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG relative luminance of a linear sRGB color."""
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _encode(channel: float) -> float:
    """Linear light to the sRGB transfer curve, where browsers blend translucent colors."""
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _decode(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


RGB = tuple[float, float, float]
"""A linear sRGB color."""


def over(top: str, alpha: float, bottom: RGB) -> RGB:
    """``top`` (an oklch token) at ``alpha`` times its own alpha, composited over ``bottom`` the
    way a browser does, in sRGB-encoded space."""
    red, green, blue, own = oklch(top)
    weight = alpha * own
    mixed = (
        _decode(weight * _encode(t) + (1 - weight) * _encode(b))
        for t, b in zip((red, green, blue), bottom, strict=True)
    )
    first, second, third = mixed
    return (first, second, third)


def opaque(token: str) -> RGB:
    """An opaque oklch token as linear sRGB; a translucent one has nothing to sit on."""
    red, green, blue, alpha = oklch(token)
    assert alpha == 1, f"{token} is translucent and needs a background"
    return (red, green, blue)


def contrast_of(first: RGB, second: RGB) -> float:
    """WCAG contrast of two linear sRGB colors."""
    darker, lighter = sorted((luminance(first), luminance(second)))
    return (lighter + 0.05) / (darker + 0.05)


def contrast(fore: str, back: str) -> float:
    """WCAG contrast of two oklch tokens; a translucent foreground is blended over the back."""
    under = opaque(back)
    return contrast_of(over(fore, 1.0, under), under)


# --- Computed style -----------------------------------------------------------------------------

_INHERITED = {
    "fill",
    "fill-opacity",
    "stroke",
    "stroke-opacity",
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "letter-spacing",
}
TOKEN_SELECTORS = {":root", ".dark"}


def _specificity(selector: str, element: ET.Element) -> int | None:
    """``selector``'s specificity when it matches ``element`` (``type``, ``.class``,
    ``type.class``), else ``None``."""
    match = re.fullmatch(r"([a-zA-Z]+)?((?:\.[\w-]+)*)", selector)
    if not match or not (match.group(1) or match.group(2)):
        return None
    tag = match.group(1)
    wanted = {name for name in match.group(2).split(".") if name}
    if tag and tag != element.tag.removeprefix(SVG_NS):
        return None
    if not wanted <= classes(element):
        return None
    return (1 if tag else 0) + 10 * len(wanted)


def computed(root: ET.Element, element: ET.Element) -> dict[str, str]:
    """The style a browser gives ``element``: matching rules by specificity and order, inherited
    properties from its ancestors, and ``opacity`` multiplied down the tree."""
    rules = [
        (selector, body)
        for selector, body in css_rules(style_of(root))
        if selector not in TOKEN_SELECTORS
    ]
    parents = {child: parent for parent in root.iter() for child in parent}
    chain = [element]
    while chain[-1] in parents:
        chain.append(parents[chain[-1]])
    style: dict[str, str] = {}
    opacity = 1.0
    for node in reversed(chain):
        matched = sorted(
            (
                (spec, order, body)
                for order, (selector, body) in enumerate(rules)
                if (spec := _specificity(selector, node)) is not None
            ),
            key=lambda item: (item[0], item[1]),
        )
        own: dict[str, str] = {}
        for _, _, body in matched:
            own.update(body)
        opacity *= float(own.get("opacity", "1"))
        style = {**{k: v for k, v in style.items() if k in _INHERITED}, **own}
    style["opacity"] = f"{opacity:g}"
    return style
