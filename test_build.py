#!/usr/bin/env python3
"""Structural checks on the generated SVG.

These do not assert that the art *looks* right - that is a judgement call
settled by rendering it and looking. They catch the silent corruption a
render might not make obvious: a sheared layer, an unmapped colour, or a
CSS rule pointing at a group that no longer exists.
"""
import re, sys, xml.etree.ElementTree as ET
import build


def check_grids_rectangular():
    """A ragged row shears every row below it, often subtly."""
    for name, mirror in (("skull", True), ("shades", False), ("fedora", True)):
        g = build.Grid.load(name, mirror)     # Grid.__init__ raises on ragged
        assert g.w > 0 and g.h > 0, name
    return "sprite grids rectangular"


def check_palette_complete():
    """Grid.load raises on unmapped chars; assert nothing is unused either."""
    used = set()
    for name, mirror in (("skull", True), ("shades", False), ("fedora", True)):
        used |= {c for r in build.Grid.load(name, mirror).rows for c in r if c != "."}
    for rects in build.build_scene().layers.values():
        used |= {r[4] for r in rects}
    unknown = used - set(build.PALETTE)
    assert not unknown, f"unmapped chars: {sorted(unknown)}"
    unused = set(build.PALETTE) - used
    assert not unused, f"dead palette entries: {sorted(unused)}"
    return f"palette exact ({len(used)} colours, none dead)"


def check_svg_wellformed(svg):
    ET.fromstring(svg)
    return "SVG parses as XML"


def check_css_targets_exist(svg):
    """Every #id the timeline animates must be a group that got emitted."""
    ids = set(re.findall(r'id="([^"]+)"', svg))
    refs = set(re.findall(r"#([A-Za-z][\w-]*)", build.css()))
    missing = refs - ids
    assert not missing, f"CSS animates missing ids: {sorted(missing)}"
    # and every frame layer must actually be referenced, or it is dead art
    frames = {i for i in ids if re.search(r"-\d+$", i)}
    orphan = frames - refs
    assert not orphan, f"frame layers never animated: {sorted(orphan)}"
    return f"{len(refs)} CSS targets all present, no orphan frames"


if __name__ == "__main__":
    svg = build.render(build.build_scene(), 1)
    results = [check_grids_rectangular(), check_palette_complete(),
               check_svg_wellformed(svg), check_css_targets_exist(svg)]
    for r in results:
        print(f"  ok  {r}")
    print(f"{len(results)} checks passed")
