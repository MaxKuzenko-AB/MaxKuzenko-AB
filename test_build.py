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
    missing = [c for c in build.TITLE_TEXT if c != " " and c not in build.FONT]
    assert not missing, f"no glyph drawn for {missing}"
    drawn = {c for c in build.TITLE_TEXT if c != " "}
    return f"title parses, {len(drawn)} distinct glyphs drawn"


def check_glyphs_rectangular():
    """A ragged row in hand-typed glyph art shears every row below it, which
    is easy to miss reading the source."""
    for ch, rows in build.FONT.items():
        widths = {len(r) for r in rows}
        assert len(widths) == 1, f"glyph {ch!r} has mixed row widths {widths}"
        assert len(rows) == build.CAP_H, \
            f"glyph {ch!r} is {len(rows)} rows, want {build.CAP_H}"
    return f"{len(build.FONT)} glyphs rectangular at cap height {build.CAP_H}"


def check_title_gradient_covers_caps():
    """Regression guard. The gradient must span exactly the cap band, in the
    same coordinate space the glyph rects are drawn in. Measuring it in a
    different space once put the ramp outside the letters entirely and
    rendered them a single flat colour."""
    svg = build.render_title()
    m = re.search(r'y1="(-?[0-9.]+)" x2="0" y2="(-?[0-9.]+)"', svg)
    span = (float(m.group(1)), float(m.group(2)))
    assert span == (build.CAP_TOP, build.CAP_BOT), \
        f"gradient spans {span}, want {(build.CAP_TOP, build.CAP_BOT)}"
    offs = [float(o) for o, _ in build.FIRE]
    assert offs == sorted(offs), "gradient stops out of order"
    assert offs[0] == 0 and offs[-1] == 100, "ramp must cover the full band"
    return f"fire gradient spans the cap band in {len(offs)} stops"


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
               check_glyphs_rectangular(),
               check_title_gradient_covers_caps(),
               check_readme_matches_timings()]
    for r in results:
        print(f"  ok  {r}")
    print(f"{len(results)} checks passed")
