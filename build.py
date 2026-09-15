#!/usr/bin/env python3
"""Build the animated 8-bit Venice Beach banner.

Everything is procedural: the scene is pure geometry, so there are no sprite
files. Chars map to hex via palette.json; adjacent same-colour pixels are
run-length merged into single <rect>s.

Nothing plays once. Every animation is an infinite loop.
"""
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).parent
PALETTE = {k: v for k, v in json.loads((ROOT / "palette.json").read_text()).items()
           if not k.startswith("_")}

W, H = 320, 40                 # letterbox strip; scale 3 -> 960x120
# Doubling W/H and every literal below halves the apparent pixel size
# without changing the rendered dimensions.
HORIZON, SHORE, SAND = 14, 26, 30


class Scene:
    """Named layers of (x, y, w, h, char) rects."""
    def __init__(self):
        self.layers = {}

    def box(self, name, x, y, w, h, c):
        if w > 0 and h > 0:
            self.layers.setdefault(name, []).append((x, y, w, h, c))

    def px(self, name, x, y, c):
        self.box(name, x, y, 1, 1, c)

    def disc(self, name, cx, cy, r, c):
        for dy in range(-r, r + 1):
            half = int((r * r - dy * dy) ** 0.5)
            self.box(name, cx - half, cy + dy, half * 2 + 1, 1, c)


# ---------------------------------------------------------------- sky and sea

SKY_RAMP = (("1", 4), ("A", 4), ("2", 4), ("3", 2))


def dither(sc, y, c, phase=0):
    """50% checkerboard: the classic 8-bit band blend. Sparser stipples read
    as dotted lines rather than a gradient."""
    for x in range(phase, W, 2):
        sc.px("sky", x, y, c)


def sky(sc):
    y = 0
    for c, hh in SKY_RAMP:
        sc.box("sky", 0, y, W, hh, c)
        y += hh
    prev = None
    for i, (c, hh) in enumerate(SKY_RAMP):
        if prev and hh >= 4:          # only wide boundaries benefit
            dither(sc, sum(h for _, h in SKY_RAMP[:i]), prev, i % 2)
        prev = c
    sc.disc("sky", 240, 8, 6, "y")
    sc.disc("sky", 240, 8, 4, "o")


CLOUD_SHAPES = {"s": ((4, 8), (0, 16), (2, 12)),
                "m": ((6, 14), (0, 26), (3, 20))}


def cloud(sc, x, y, kind):
    rows = CLOUD_SHAPES[kind]
    for i, (dx, ww) in enumerate(rows):
        sc.box("clouds", x + dx, y + i, ww, 1, "p" if i == len(rows) - 1 else "o")


def clouds(sc):
    for ox in (0, W):              # tiled to 2W so a -W scroll wraps seamlessly
        cloud(sc, ox + 20, 2, "m")
        cloud(sc, ox + 104, 1, "s")
        cloud(sc, ox + 176, 4, "s")
        cloud(sc, ox + 272, 2, "m")


def sea(sc):
    for y0, y1, c in ((HORIZON, 18, "5"), (18, 22, "6"), (22, SHORE, "7")):
        sc.box("sea", 0, y0, W, y1 - y0, c)
    sc.box("sea", 0, HORIZON, W, 1, "8")       # crisp horizon glint


def beach(sc):
    sc.box("sand", 0, SHORE, W, SAND - SHORE, "c")     # wet sand
    sc.box("sand", 0, SAND, W, H - SAND, "s")          # dry sand
    seed = 0x9E3779B9
    for _ in range(120):                                # deterministic speckle
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = (seed >> 7) % W
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = SAND + 1 + (seed >> 11) % (H - SAND - 1)
        sc.px("sand", x, y, "b" if (seed >> 3) % 3 else "a")


# ---------------------------------------------------------------- ambient frames

ROLLER_FRAMES = FOAM_FRAMES = 4


def rollers(sc):
    """Dashed foam crests creeping shoreward; the phase reset reads as a break."""
    for f in range(ROLLER_FRAMES):
        for j, base in enumerate((17, 21)):
            y = base + f % 3
            x, k = -(f * 18 + j * 11), 0
            while x < W:
                dash, gap = ((18, 38), (28, 50), (14, 34), (24, 44))[(k + j) % 4]
                if x + dash > 0:
                    sc.box(f"roller-{f}", max(0, x), y,
                           min(dash, W - max(0, x)), 1, "8")
                x += dash + gap
                k += 1


def shore_foam(sc):
    """The waterline runs up the wet sand and slides back."""
    for f in range(FOAM_FRAMES):
        adv = (0, 2, 4, 2)[f]
        sc.box(f"foam-{f}", 0, SHORE - 2 + adv, W, 2, "8")
        x, k = f * 10, 0
        while x < W:                           # irregular scalloped edge
            ww, gap = ((5, 15), (9, 11), (3, 17), (7, 13))[k % 4]
            sc.box(f"foam-{f}", x % W, SHORE + adv, min(ww, W - x % W), 1, "8")
            x += ww + gap
            k += 1


# ---------------------------------------------------------------- palms

def bezier(p0, p1, p2, steps=60):
    """Sample a quadratic curve, dropping duplicate pixels. Returns (x, y, t)."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        k = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        x = round(k[0] * p0[0] + k[1] * p1[0] + k[2] * p2[0])
        y = round(k[0] * p0[1] + k[1] * p1[1] + k[2] * p2[1])
        if not out or (x, y) != out[-1][:2]:
            out.append((x, y, t))
    return out


def frond(sc, name, cx, cy, end, ctrl, scale):
    """One blade: a Bezier spine with thickness tapering base -> tip.
    Stepping one column per iteration merges the blades into a flat cap."""
    p1 = (cx + ctrl[0] * scale, cy + ctrl[1] * scale)
    p2 = (cx + end[0] * scale, cy + end[1] * scale)
    for x, y, t in bezier((cx, cy), p1, p2):
        thick = 6 if t < 0.55 else 4 if t < 0.85 else 2
        top = y - thick // 2
        sc.box(name, x, top, 1, thick, "g")
        sc.px(name, x, top, "h")                       # sunlit upper edge
        if thick > 1:
            sc.px(name, x, top + thick - 1, "i")       # shaded underside


FRONDS = (((-15, 6), (-10, -5)), ((-9, -2), (-6, -7)),
          ((0, -8), (0, -8)),
          ((9, -2), (6, -7)), ((15, 6), (10, -5)))
PALM_WIND = (-4.0, 0.0, 4.0, 0.0)      # back and forth, so the loop never snaps
TREES = (("palm-far", 278, 32, 21, 0.5, 0.84),
         ("palm-near", 40, 38, 27, -0.4, 1.16))


def palm_trunk(sc, name, bx, by, height, lean):
    for i in range(height):
        y, t = by - i, i / (height - 1)
        x = bx + round(lean * t * t * 12)
        wide = 6 if t < 0.4 else 4
        sc.box(name, x, y, wide, 1, "t")
        sc.px(name, x if lean > 0 else x + wide - 1, y, "u")


def palm_crown(sc, name, bx, by, height, lean, scale, wind):
    """wind bends every blade downwind; swapping wind values animates the sway."""
    cx, cy = bx + round(lean * 12) + 2, by - height
    for end, ctrl in FRONDS:
        frond(sc, name, cx, cy,
              (end[0] + wind, end[1] + abs(wind) * 0.4),
              (ctrl[0] + wind * 0.5, ctrl[1] + abs(wind) * 0.3), scale)
    sc.box(name, cx - 4, cy - 2, 10, 6, "i")           # crown knot
    sc.box(name, cx - 1, cy - 2, 3, 3, "g")


def palms(sc):
    for name, bx, by, h, lean, scale in TREES:
        palm_trunk(sc, f"{name}-trunk", bx, by, h, lean)
        for f, wind in enumerate(PALM_WIND):
            palm_crown(sc, f"{name}-{f}", bx, by, h, lean, scale, wind)


# ---------------------------------------------------------------- output

def merge(rects):
    """Rasterise to a pixel map, then RLE each row. Kills per-pixel rects and
    resolves overdraw, so duplicated pixels stop costing anything."""
    grid = {}
    for x, y, w, h, c in rects:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                grid[(xx, yy)] = c
    rows = {}
    for (x, y), c in grid.items():
        rows.setdefault(y, {})[x] = c
    out = []
    for y in sorted(rows):
        row = rows[y]
        rx = rc = None
        rn = 0
        for x in sorted(row):
            c = row[x]
            if rx is not None and x == rx + rn and c == rc:
                rn += 1
            else:
                if rx is not None:
                    out.append((rx, y, rn, 1, rc))
                rx, rc, rn = x, c, 1
        if rx is not None:
            out.append((rx, y, rn, 1, rc))
    return out


def emit(rects):
    by_colour = {}
    for x, y, w, h, c in rects:
        by_colour.setdefault(c, []).append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
    return "".join(f'<g fill="{PALETTE[c]}">{"".join(v)}</g>'
                   for c, v in by_colour.items())


# Periods are deliberately non-harmonic. Shared factors would make the whole
# scene visibly pulse in unison every few seconds.
FRAME_SETS = [("palm-near", len(PALM_WIND), 2.0),
              ("palm-far", len(PALM_WIND), 2.5),
              ("roller", ROLLER_FRAMES, 1.5),
              ("foam", FOAM_FRAMES, 3.1)]
# Full re-sync of 2.0 / 2.5 / 1.5 / 3.1 is 30s apart, so nothing visibly
# pulses in unison.
CLOUD_DRIFT = 18.0            # seconds for one full 320px wrap, not a frame period

ORDER = (["sky", "clouds", "sea"]
         + [f"roller-{f}" for f in range(ROLLER_FRAMES)] + ["sand"]
         + [f"foam-{f}" for f in range(FOAM_FRAMES)]
         + ["palm-far-trunk"] + [f"palm-far-{f}" for f in range(len(PALM_WIND))]
         + ["palm-near-trunk"] + [f"palm-near-{f}" for f in range(len(PALM_WIND))])


def css():
    frame_ids = [f"{p}-{i}" for p, n, _ in FRAME_SETS for i in range(n)]
    out = [",".join(f"#{i}" for i in frame_ids) + "{opacity:0}",
           # quantised to whole grid pixels: a continuous slide puts pixels on
           # half-coordinates and blurs the grid
           f"#clouds{{animation:drift {CLOUD_DRIFT}s steps(320,end) infinite}}",
           "@keyframes drift{0%{transform:translate(0)}"
           "100%{transform:translate(-320px)}}"]
    for pre, n, period in FRAME_SETS:
        for i in range(n):
            out.append(f"#{pre}-{i}{{animation:cyc{n} {period}s steps(1,end) "
                       f"{i * period / n:.3f}s infinite}}")
        share = 100.0 / n
        out.append(f"@keyframes cyc{n}{{0%,{share - 0.01:.2f}%{{opacity:1}}"
                   f"{share:.2f}%,100%{{opacity:0}}}}")
    return "".join(out)


def render(sc, scale, animate=True):
    body = "".join(f'<g id="{n}">{emit(merge(sc.layers[n]))}</g>'
                   for n in ORDER if n in sc.layers)
    style = f"<style>{css()}</style>" if animate else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W*scale}" height="{H*scale}" shape-rendering="crispEdges" '
            f'role="img" aria-label="Animated 8-bit Venice Beach: swaying palms, '
            f'rolling surf and drifting clouds">'
            f'{style}<rect width="{W}" height="{H}" fill="{PALETTE["1"]}"/>'
            f'{body}</svg>')


# ---------------------------------------------------------------- title
# Glyph outlines were extracted from Impact once, in a throwaway venv, and
# committed as path data. The repo therefore needs no font files and no
# fontTools at build time, and the type renders identically for every viewer
# regardless of which fonts they happen to have installed.
TITLE = json.loads((ROOT / "title-glyphs.json").read_text())
CAP = TITLE["cap"]
# derive the box from the measured advance: hardcoding it let the type overflow
TITLE_W = round(TITLE["advance"]) + 70
TITLE_H = round(CAP) + 46
BASELINE = round(CAP) + 22

# 80s chrome type: a hard horizontal break at the midline is the whole trick.
# A smooth blue-to-violet ramp reads as a soft gradient, not as chrome.
CHROME = (("0", "#ffffff"), ("8", "#eaf5ff"), ("26", "#7cc0f0"),
          ("44", "#2f6fc4"), ("49", "#14418f"),
          ("49.6", "#1a0f2e"),
          ("58", "#3d2468"), ("74", "#7a58b4"), ("88", "#c3aee4"),
          ("96", "#f2ecfb"), ("100", "#ffffff"))


def stars(n=110):
    """Deterministic scatter, so rebuilds are byte-identical."""
    out, seed = [], 0xC0FFEE
    for _ in range(n):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = (seed >> 6) % TITLE_W
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = (seed >> 6) % TITLE_H
        r = (1.4, 0.9, 0.6)[(seed >> 3) % 3]
        o = (1.0, 0.65, 0.4)[(seed >> 5) % 3]
        out.append(f'<circle cx="{x}" cy="{y}" r="{r}" opacity="{o}"/>')
    return f'<g fill="#fff">{"".join(out)}</g>'


def render_title():
    stops = "".join(f'<stop offset="{o}%" stop-color="{c}"/>' for o, c in CHROME)
    dx = round((TITLE_W - TITLE["advance"]) / 2, 2)
    paths = "".join(f'<path d="{g["d"]}"/>' for g in TITLE["glyphs"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {TITLE_W} {TITLE_H}" width="{TITLE_W}" '
            f'height="{TITLE_H}" role="img" aria-label="{TITLE["text"]}">'
            f'<defs><linearGradient id="chrome" gradientUnits="userSpaceOnUse" '
            f'x1="0" y1="{-CAP}" x2="0" y2="0">{stops}</linearGradient>'
            f'</defs><rect width="{TITLE_W}" height="{TITLE_H}" fill="#04040a"/>'
            f'{stars()}'
            # paint-order puts the white stroke behind the fill, so the letters
            # keep their full weight instead of being eaten into
            f'<g transform="translate({dx},{BASELINE})" fill="url(#chrome)" '
            f'stroke="#ffffff" stroke-width="7" stroke-linejoin="round" '
            f'paint-order="stroke">{paths}</g></svg>')


def build_scene():
    sc = Scene()
    sky(sc); clouds(sc); sea(sc); rollers(sc); beach(sc); shore_foam(sc); palms(sc)
    return sc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=int, default=3)
    p.add_argument("--static", action="store_true", help="drop the CSS timeline")
    p.add_argument("--title", action="store_true", help="render the title instead")
    a = p.parse_args()
    if a.title:
        out = render_title()
        print(out, end="")
        print(f"title: {len(TITLE['glyphs'])} glyphs from {TITLE['font']}, "
              f"{len(out)} bytes", file=sys.stderr)
        return
    sc = build_scene()
    out = render(sc, a.scale, animate=not a.static)
    print(out, end="")
    print(f"{sum(len(merge(v)) for v in sc.layers.values())} rects after merge, "
          f"{len(out)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
