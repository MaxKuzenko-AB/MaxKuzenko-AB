#!/usr/bin/env python3
"""Structural checks on the generated SVG.

These do not assert that the art *looks* right - that is a judgement call
settled by rendering it and looking. They catch the silent breakage a glance
might miss: an unmapped colour, a CSS rule pointing at a group that no longer
exists, a layer painting off-canvas, or an animation that stops.
"""
import re, xml.etree.ElementTree as ET
import build


def check_palette_exact(sc):
    used = {r[4] for rects in sc.layers.values() for r in rects}
    unknown = used - set(build.PALETTE)
    assert not unknown, f"unmapped chars: {sorted(unknown)}"
    dead = set(build.PALETTE) - used
    assert not dead, f"dead palette entries: {sorted(dead)}"
    return f"palette exact ({len(used)} colours, none dead)"


def check_svg_wellformed(svg):
    ET.fromstring(svg)
    return "SVG parses as XML"


def check_css_targets_exist(svg):
    ids = set(re.findall(r'id="([^"]+)"', svg))
    refs = set(re.findall(r"#([A-Za-z][\w-]*)", build.css()))
    missing = refs - ids
    assert not missing, f"CSS animates missing ids: {sorted(missing)}"
    orphan = {i for i in ids if re.search(r"-\d+$", i)} - refs
    assert not orphan, f"frame layers never animated: {sorted(orphan)}"
    return f"{len(refs)} CSS targets present, no orphan frames"


def check_everything_loops():
    """The banner must never settle. Any animation without `infinite` would
    play once and freeze, which is the behaviour this build removed."""
    rules = [r for r in build.css().split("}") if "animation:" in r]
    assert rules, "no animations found at all"
    finite = [r for r in rules if "infinite" not in r]
    assert not finite, f"non-looping animations: {finite}"
    return f"all {len(rules)} animations are infinite"


def check_stays_on_canvas(sc):
    """Only the cloud layer may exceed the canvas: it is tiled to 2W so the
    scroll wraps seamlessly."""
    for name, rects in sc.layers.items():
        if name == "clouds":
            continue
        for x, y, w, h, c in rects:
            assert 0 <= x and x + w <= build.W, f"{name}: x {x}..{x+w}"
            assert 0 <= y and y + h <= build.H, f"{name}: y {y}..{y+h}"
    return f"{len(sc.layers) - 1} layers within {build.W}x{build.H}"


if __name__ == "__main__":
    sc = build.build_scene()
    svg = build.render(sc, 1)
    results = [check_palette_exact(sc), check_svg_wellformed(svg),
               check_css_targets_exist(svg), check_everything_loops(),
               check_stays_on_canvas(sc)]
    for r in results:
        print(f"  ok  {r}")
    print(f"{len(results)} checks passed")
