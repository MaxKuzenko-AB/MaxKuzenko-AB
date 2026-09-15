#!/usr/bin/env python3
"""Structural checks on the generated SVG.

These do not assert that the art *looks* right - that is a judgement call
settled by rendering it and looking. They catch the silent breakage a glance
might miss: an unmapped colour, a CSS rule pointing at a group that no longer
exists, a layer painting off-canvas, or an animation that stops.
"""
import pathlib, re, xml.etree.ElementTree as ET
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


def check_title_wellformed():
    svg = build.render_title()
    ET.fromstring(svg)
    face, outline = build.title_pixels()
    assert face and outline, "title needs both a face and an outline layer"
    return f"title parses, {len(face)} face px over {len(outline)} outline px"


def check_art_rectangular():
    """A ragged row in the stored bitmap shears every row below it, and the
    art is wide enough that it would not be obvious reading the source."""
    widths = {len(r) for r in build.TITLE_ART}
    assert len(widths) == 1, f"mixed row widths {sorted(widths)}"
    bad = {c for r in build.TITLE_ART for c in r} - set("#+.")
    assert not bad, f"unknown symbols in the art: {sorted(bad)}"
    return f"art rectangular at {build.ART_W}x{build.ART_H}"


def check_face_is_not_white():
    """The source art had white letter faces on a purple outline, which made
    the letters vanish on a light background. Guard the remap: no fill in the
    title may be near-white, or the light theme breaks again."""
    svg = build.render_title()
    fills = set(re.findall(r'(?:fill|stop-color)="(#[0-9a-fA-F]{6})"', svg))
    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    glare = {f for f in fills if lum(f) > 0.93}
    assert not glare, f"near-white fills would disappear on a light page: {glare}"
    return f"{len(fills)} title fills, none near-white"


def check_title_gradient_covers_caps():
    """Regression guard. The gradient must span exactly the art band, in the
    same coordinate space the rects are drawn in. Measuring it in a different
    space once put the ramp outside the letters entirely."""
    svg = build.render_title()
    m = re.search(r'y1="(-?[0-9.]+)" x2="0" y2="(-?[0-9.]+)"', svg)
    span = (float(m.group(1)), float(m.group(2)))
    assert span == (build.CAP_TOP, build.CAP_BOT), \
        f"gradient spans {span}, want {(build.CAP_TOP, build.CAP_BOT)}"
    offs = [float(o) for o, _ in build.FIRE]
    assert offs == sorted(offs), "gradient stops out of order"
    assert offs[0] == 0 and offs[-1] == 100, "ramp must cover the full band"
    return f"fire gradient spans the art band in {len(offs)} stops"


def check_readme_matches_timings():
    """The README table is documentation only - editing it does not change the
    animation, which lives in FRAME_SETS and CLOUD_DRIFT. This guards against
    the two drifting apart, which has already happened once."""
    rd = pathlib.Path(__file__).parent.joinpath("README.md").read_text()
    documented = [float(v) for v in
                  re.findall(r"\|\s*(?:4|scrolled)\s*\|\s*([\d.]+)s\s*\|", rd)]
    actual = [p for _, _, p in build.FRAME_SETS] + [build.CLOUD_DRIFT]
    assert documented, "no timing table found in README"
    assert documented == actual, f"README says {documented}, code says {actual}"
    return f"README timing table matches code ({len(actual)} rows)"


if __name__ == "__main__":
    sc = build.build_scene()
    svg = build.render(sc, 1)
    results = [check_palette_exact(sc), check_svg_wellformed(svg),
               check_css_targets_exist(svg), check_everything_loops(),
               check_stays_on_canvas(sc), check_title_wellformed(),
               check_art_rectangular(), check_face_is_not_white(),
               check_title_gradient_covers_caps(),
               check_readme_matches_timings()]
    for r in results:
        print(f"  ok  {r}")
    print(f"{len(results)} checks passed")
