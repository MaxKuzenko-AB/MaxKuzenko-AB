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
    n = len([c for c in build.TITLE["text"] if c != " "])
    assert svg.count("<path") == n, f"{svg.count('<path')} paths for {n} letters"
    return f"title parses, {n} glyph paths"


def check_title_gradient_covers_caps():
    """Regression guard. The gradient is referenced from inside the translated
    glyph group, so its userSpaceOnUse coordinates live in that space -
    baseline at 0, cap line at -CAP. Measuring it in the outer space instead
    put the whole ramp below the letters and rendered them solid white."""
    svg = build.render_title()
    y1 = float(re.search(r'y1="(-?[\d.]+)" x2="0" y2="(-?[\d.]+)"', svg).group(1))
    y2 = float(re.search(r'y1="(-?[\d.]+)" x2="0" y2="(-?[\d.]+)"', svg).group(2))
    assert y1 == -build.CAP and y2 == 0, f"gradient spans {y1}..{y2}, want {-build.CAP}..0"
    offs = [float(o) for o, _ in build.CHROME]
    assert offs == sorted(offs), "gradient stops out of order"
    gaps = [(b - a, a) for a, b in zip(offs, offs[1:])]
    tightest, at = min(gaps)
    assert tightest < 1.0, "no hard split: chrome type needs an abrupt stop"
    return f"gradient spans the cap height, hard split at {at:.0f}%"


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
               check_title_gradient_covers_caps(),
               check_readme_matches_timings()]
    for r in results:
        print(f"  ok  {r}")
    print(f"{len(results)} checks passed")
