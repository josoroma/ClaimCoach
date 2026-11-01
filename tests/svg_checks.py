"""The self-contained SVG check shared by US-13.1 (the logo) and US-13.4 (the flow diagrams).

An SVG shown through ``<img>`` on GitHub, in an editor, or in the plugin listing must fetch
nothing and run nothing: no script or event handler, no element outside the SVG namespace, no
``href``, no ``url()`` other than a ``#`` reference to the file's own definitions, and no
processing instruction, DOCTYPE, or entity.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"
_FORBIDDEN_TAGS = {"script", "image", "foreignObject", "use", "a", "iframe", "object", "embed"}
# The lookahead also refuses a quote or space, so backtracking past an optional quote cannot
# turn ``url('#g')`` into a match.
_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?\s*(?![#'\"\s])", re.I)
_PROLOG = re.compile(r"<\?xml-stylesheet|<!DOCTYPE|<!ENTITY|@import", re.I)


def self_contained_svg(path: Path) -> ET.Element:
    """Parse ``path`` and assert it is an SVG with a title, a viewBox, and nothing it fetches.

    Args:
        path: The SVG file.

    Returns:
        The root ``<svg>`` element.
    """
    text = path.read_text(encoding="utf-8")
    found = _PROLOG.search(text)
    assert not found, f"{path.name}: {found.group(0) if found else ''} is not allowed"
    root = ET.fromstring(text)  # noqa: S314 - ours, and DOCTYPE/ENTITY are refused above
    assert root.tag == f"{SVG_NS}svg", f"{path.name}: not an SVG document"
    assert root.get("viewBox"), f"{path.name}: no viewBox"
    title = root.find(f"{SVG_NS}title")
    assert title is not None, f"{path.name}: no title"
    assert (title.text or "").strip(), f"{path.name}: no title"
    for element in root.iter():
        assert element.tag.startswith(SVG_NS), f"{path.name}: {element.tag} is outside SVG"
        tag = element.tag.removeprefix(SVG_NS)
        assert tag not in _FORBIDDEN_TAGS, f"{path.name}: <{tag}> is not allowed"
        assert not _EXTERNAL_URL.search(element.text or ""), f"{path.name}: external url()"
        for name, value in element.attrib.items():
            assert not name.lower().startswith("on"), f"{path.name}: event handler {name}"
            assert not name.endswith("href"), f"{path.name}: {name} references another file"
            assert not _EXTERNAL_URL.search(value), f"{path.name}: external url()"
    return root
