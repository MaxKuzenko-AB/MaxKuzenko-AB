#!/usr/bin/env python3
"""Build the animated 8-bit Venice Beach SVG.

Art comes from two places:
  - art/*.txt   ASCII grids, one char per pixel, '.' transparent.
                Used where every pixel matters (skull, glasses, fedora).
  - Scene.*     procedural primitives. Used for geometry (sky, sea,
                sand, palms) where hand-typing a 160x90 grid is silly.

Chars map to hex via palette.json. Rects are run-length merged.
"""
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).parent
ART = ROOT / "art"
PALETTE = {k: v for k, v in json.loads((ROOT / "palette.json").read_text()).items()
           if not k.startswith("_")}

W, H = 160, 90
HORIZON = 44
SHORE = 57
SAND = 63


class Grid:
    def __init__(self, rows):
        self.rows, self.h = rows, len(rows)
        self.w = len(rows[0]) if rows else 0
        for i, r in enumerate(rows):
            if len(r) != self.w:
                raise ValueError(f"ragged row {i}: width {len(r)} != {self.w}")

    @classmethod
    def load(cls, name, mirror=False):
        path = ART / f"{name}.txt"
        if not path.exists():
            raise SystemExit(f"no such sprite: {path}")
        rows = [l.rstrip("\n") for l in path.read_text().splitlines()]
        rows = [l for l in rows if l and not l.startswith("#")]
        g = cls(rows)
        if mirror:
            g = cls([r + r[::-1] for r in g.rows])
        used = {c for r in g.rows for c in r if c != "."}
        missing = used - set(PALETTE)
        if missing:
            raise SystemExit(f"{name}: palette missing {sorted(missing)}")
        return g

    def rects(self, ox=0, oy=0):
        out = []
        for y, row in enumerate(self.rows):
            x = 0
            while x < self.w:
                c = row[x]
                if c == ".":
                    x += 1
                    continue
                run = 1
                while x + run < self.w and row[x + run] == c:
                    run += 1
                out.append((ox + x, oy + y, run, 1, c))
                x += run
        return out


class Scene:
    """Named layers of (x, y, w, h, char) rects."""
    def __init__(self):
        self.layers = {}

    def add(self, name, rects):
        self.layers.setdefault(name, []).extend(rects)

    def box(self, name, x, y, w, h, c):
        if w > 0 and h > 0:
            self.add(name, [(x, y, w, h, c)])

    def px(self, name, x, y, c):
        self.box(name, x, y, 1, 1, c)

    def sprite(self, name, grid, x, y):
        self.add(name, grid.rects(x, y))

    def disc(self, name, cx, cy, r, c):
        """Pixel circle: one horizontal run per row."""
        for dy in range(-r, r + 1):
            half = int((r * r - dy * dy) ** 0.5)
            self.box(name, cx - half, cy + dy, half * 2 + 1, 1, c)


# ---------------------------------------------------------------- background

def dither(sc, name, y, c, phase=0):
    """50% checkerboard across a row: the classic 8-bit band blend.
    Sparser stipples read as dotted lines, not as a gradient."""
    for x in range(phase, W, 2):
        sc.px(name, x, y, c)


def sky(sc):
    # bands get thinner toward the horizon: real skies brighten fastest there,
    # and even-height bands read as venetian stripes
    ramp = (("1", 14), ("A", 9), ("2", 7), ("B", 5), ("3", 4), ("C", 3), ("4", 2))
    y = 0
    for c, hh in ramp:
        sc.box("sky", 0, y, W, hh, c)
        y += hh
    prev = None
    for i, (c, hh) in enumerate(ramp):
        if prev and hh >= 4:                 # only the wide boundaries need it
            dither(sc, "sky", sum(h for _, h in ramp[:i]), prev, i % 2)
        prev = c
    sc.disc("sky", 130, 13, 7, "y")          # low afternoon sun
    sc.disc("sky", 130, 13, 5, "o")


CLOUD_SHAPES = {
    "s": ((3, 6), (1, 11), (0, 13), (2, 9)),
    "m": ((5, 9), (2, 16), (0, 20), (3, 14)),
    "l": ((6, 12), (3, 20), (0, 26), (4, 18)),
}


def cloud(sc, name, x, y, kind):
    """Lumpy cumulus: per-row offset+width, shadowed underside."""
    rows = CLOUD_SHAPES[kind]
    for i, (dx, ww) in enumerate(rows):
        c = "p" if i == len(rows) - 1 else "o"
        sc.box(name, x + dx, y + i, ww, 1, c)


def clouds(sc):
    # tiled to 2*W so a -W scroll wraps seamlessly
    for ox in (0, W):
        cloud(sc, "clouds", ox + 10, 7, "m")
        cloud(sc, "clouds", ox + 56, 3, "s")
        cloud(sc, "clouds", ox + 88, 13, "l")
        cloud(sc, "clouds", ox + 138, 8, "s")


def sea(sc):
    for y0, y1, c in ((HORIZON, 47, "5"), (47, 51, "6"), (51, SHORE, "7")):
        sc.box("sea", 0, y0, W, y1 - y0, c)
    sc.box("sea", 0, HORIZON, W, 1, "8")     # crisp horizon glint


def beach(sc):
    sc.box("sand", 0, SHORE, W, SAND - SHORE, "c")   # wet sand
    sc.box("sand", 0, SAND, W, H - SAND, "s")        # dry sand
    # deterministic speckle so the sand is not a flat slab
    seed = 0x9E3779B9
    for _ in range(120):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = (seed >> 7) % W
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = SAND + 1 + (seed >> 11) % (H - SAND - 1)
        sc.px("sand", x, y, "b" if (seed >> 3) % 3 else "a")


ROLLER_FRAMES = FOAM_FRAMES = 4


def rollers(sc):
    """Dashed foam crests creeping shoreward; the phase reset reads as a break."""
    for f in range(ROLLER_FRAMES):
        name = f"roller-{f}"
        for j, base in enumerate((46, 50, 54)):
            y = base + f
            dash, gap = 7 + j * 2, 13 + j * 3
            phase = (f * 5 + j * 7) % (dash + gap)
            x = -phase
            while x < W:
                if x + dash > 0:
                    sc.box(name, max(0, x), y, min(dash, W - max(0, x)), 1, "8")
                x += dash + gap


def shore_foam(sc):
    """The waterline runs up the wet sand and slides back."""
    for f in range(FOAM_FRAMES):
        name = f"foam-{f}"
        adv = (0, 2, 3, 1)[f]
        sc.box(name, 0, SHORE - 1 + adv, W, 2, "8")
        for x in range(0, W, 9):                    # scalloped leading edge
            sc.px(name, (x + f * 4) % W, SHORE + 1 + adv, "8")


# ---------------------------------------------------------------- palms

def bezier(p0, p1, p2, steps=80):
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


def frond(sc, name, cx, cy, end, ctrl, scale=1.0):
    """One blade: a Bezier spine with thickness tapering base -> tip."""
    p0 = (cx, cy)
    p1 = (cx + ctrl[0] * scale, cy + ctrl[1] * scale)
    p2 = (cx + end[0] * scale, cy + end[1] * scale)
    for x, y, t in bezier(p0, p1, p2):
        thick = 4 if t < 0.25 else 3 if t < 0.5 else 2 if t < 0.8 else 1
        top = y - thick // 2
        sc.box(name, x, top, 1, thick, "g")
        sc.px(name, x, top, "h")                      # sunlit upper edge
        if thick > 1:
            sc.px(name, x, top + thick - 1, "i")      # shaded underside


# end point and control point per frond, relative to the crown
FRONDS = (
    ((-17, 9), (-12, -8)), ((-14, 3), (-9, -9)), ((-8, -7), (-6, -10)),
    ((0, -11), (1, -10)),
    ((8, -7), (6, -10)), ((14, 3), (9, -9)), ((17, 9), (12, -8)),
)


def palm_trunk(sc, name, bx, by, height, lean):
    for i in range(height):
        y = by - i
        t = i / (height - 1)
        x = bx + round(lean * t * t * 11)
        wide = 4 if t < 0.3 else 3 if t < 0.75 else 2
        sc.box(name, x, y, wide, 1, "t")
        sc.px(name, x if lean > 0 else x + wide - 1, y, "u")


def palm_crown(sc, name, bx, by, height, lean, scale=1.0, wind=0.0):
    """wind bends every blade downwind; swapping wind values animates the sway."""
    cx = bx + round(lean * 11) + 1
    cy = by - height
    for end, ctrl in FRONDS:
        e = (end[0] + wind, end[1] + abs(wind) * 0.4)
        c = (ctrl[0] + wind * 0.5, ctrl[1] + abs(wind) * 0.3)
        frond(sc, name, cx, cy, e, c, scale)
    sc.box(name, cx - 2, cy - 1, 4, 3, "i")
    sc.px(name, cx - 1, cy - 1, "g")


PALM_WIND = (-2.0, 0.0, 2.0, 0.0)      # back-and-forth, so the loop never snaps
TREES = (("palm-far", 136, 69, 23, 0.55, 0.66),
         ("palm-near", 18, 76, 34, -0.45, 1.0))


def palms(sc):
    for name, bx, by, h, lean, scale in TREES:
        palm_trunk(sc, f"{name}-trunk", bx, by, h, lean)
        for f, wind in enumerate(PALM_WIND):
            palm_crown(sc, f"{name}-{f}", bx, by, h, lean, scale, wind)



# ---------------------------------------------------------------- figure
# Torso and shirt share ONE half-width profile, so the shirt can never
# drift off the body. Index 0 is the base of the neck.
TORSO = (9, 11, 14, 18, 24, 30, 35, 38, 40, 40, 39, 38, 37, 36, 35, 34,
         33, 33, 32, 32, 31, 31, 30, 30, 30, 30, 30, 31, 31, 32,
         32, 33, 33, 34, 34, 35, 35, 36, 36, 37)
TORSO_X, TORSO_Y = 80, 50
HEAD_X, HEAD_Y = 60, 8


def profile_row(sc, name, cx, y, hw, ramp):
    """Draw one symmetric row, colouring by distance in from the edge."""
    for d in range(hw):
        c = ramp(d, hw)
        if c:
            sc.px(name, cx - hw + d, y, c)
            sc.px(name, cx + hw - 1 - d, y, c)


def chrome_torso(sc, name="torso"):
    def ramp(d, hw):
        return "K" if d == 0 else "D" if d == 1 else "M" if d < 4 else "L"
    for i, hw in enumerate(TORSO):
        y = TORSO_Y + i
        if y >= H:
            break
        profile_row(sc, name, TORSO_X, y, hw, ramp)
        if 6 <= i <= 9:                                # shoulder sheen
            sc.box(name, TORSO_X - hw + 5, y, 6, 1, "W")
            sc.box(name, TORSO_X + hw - 11, y, 6, 1, "W")


def collar_cut(i):
    """Half-width of the open-neck V at torso row i."""
    return max(0, 9 - (i - 3) * 3 // 5) if 3 <= i <= 18 else 0


HIBISCUS = ("..N..", ".NnN.", "NnynN", ".NnN.", "..N..")
LEAF = (".vv.", "vVVv", ".v..")


def stamp(sc, name, rows, x, y, inside):
    for dy, row in enumerate(rows):
        for dx, c in enumerate(row):
            if c != "." and inside(x + dx, y + dy):
                sc.px(name, x + dx, y + dy, c)


def shirt(sc, name="shirt"):
    """Cream hawaiian over the same silhouette, open collar showing chrome."""
    occupied = {}
    for i, hw in enumerate(TORSO):
        y = TORSO_Y + i
        if y >= H:
            break
        occupied[y] = hw

    def inside(x, y):
        hw = occupied.get(y)
        return hw is not None and TORSO_X - hw <= x < TORSO_X + hw

    def ramp(d, hw):
        return "w" if d < 2 else "f"
    for y, hw in occupied.items():
        i = y - TORSO_Y
        if i < 3:
            continue                                   # bare neck above the collar
        cut = collar_cut(i)
        for d in range(hw):
            for x in (TORSO_X - hw + d, TORSO_X + hw - 1 - d):
                if abs(x - TORSO_X) >= cut:            # V stays open -> chrome
                    sc.px(name, x, y, ramp(d, hw))


    # floral: tighter staggered lattice, three variants so it is not a grid
    for row, y in enumerate(range(TORSO_Y + 8, H, 7)):
        stag = (row % 3) * 4
        for col, x in enumerate(range(TORSO_X - 38 + stag, TORSO_X + 38, 11)):
            if (row * 7 + col * 5) % 3 == 0:
                continue                           # breathing room
            kind = (row * 5 + col * 3) % 4
            if kind == 0:
                stamp(sc, name, LEAF, x, y + 1, inside)
            elif kind == 3:
                stamp(sc, name, LEAF, x + 1, y, inside)
            else:
                stamp(sc, name, HIBISCUS, x, y, inside)


def figure(sc):
    chrome_torso(sc)
    sc.sprite("head", Grid.load("skull", mirror=True), HEAD_X, HEAD_Y)
    shirt(sc)
    sc.sprite("shades", Grid.load("shades"), 62, 24)
    sc.sprite("hat", Grid.load("fedora", mirror=True), 54, 0)

    # the optic has to animate independently, so split it off the skull
    head = Grid.load("skull", mirror=True)
    for x, y, w, h, c in head.rects(HEAD_X, HEAD_Y):
        if c in "Rr":
            sc.add("optic-0", [(x, y, w, h, c)])
            sc.add("optic-1", [(x, y, w, h, "G")])
        else:
            sc.add("head", [(x, y, w, h, c)])
    shirt(sc)
    sc.sprite("shades", Grid.load("shades"), 62, 24)
    sc.sprite("hat", Grid.load("fedora", mirror=True), 54, 0)


# ---------------------------------------------------------------- output

def merge(rects):
    """Rasterise to a pixel map, then RLE each row. Kills per-pixel rects
    and resolves overdraw, so duplicated pixels stop costing anything."""
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


# ---- timeline (seconds). One-shots run once and hold; ambient loops forever.
T_CUT, T_WIPE = 2.0, 2.0
T_SHADES, T_SHIRT, T_HAT = 4.0, 5.5, 7.0

PALM_FRAMES = len(PALM_WIND)
FRAME_SETS = [                       # (layer prefix, count, period seconds)
    ("palm-near", PALM_FRAMES, 1.2),
    ("palm-far", PALM_FRAMES, 1.5),  # deliberately not 1.2: no lockstep sway
    ("roller", ROLLER_FRAMES, 0.5),
    ("foam", FOAM_FRAMES, 3.1),
    ("optic", 2, 1.8),
]

BG = (["sky", "clouds", "sea"]
      + [f"roller-{f}" for f in range(ROLLER_FRAMES)]
      + ["sand"]
      + [f"foam-{f}" for f in range(FOAM_FRAMES)]
      + ["palm-far-trunk"] + [f"palm-far-{f}" for f in range(PALM_FRAMES)]
      + ["palm-near-trunk"] + [f"palm-near-{f}" for f in range(PALM_FRAMES)])
FIGURE = ["torso", "shirt", "head", "optic-0", "optic-1", "shades", "hat"]


def css():
    frame_ids = [f"{pre}-{i}" for pre, n, _ in FRAME_SETS for i in range(n)]
    out = [
        # frame layers are hidden by default; each cycle switches its own on
        ",".join(f"#{i}" for i in frame_ids) + "{opacity:0}",
        "#figure{transform-box:view-box;transform-origin:80px 15px;"
        f"animation:zoomcut {T_CUT}s steps(1,end) 0s 1 both,"
        f"lightup 1s steps(3,end) {T_CUT}s 1 both}}",
        "@keyframes zoomcut{0%{transform:scale(2)}100%{transform:scale(1)}}",
        "@keyframes lightup{0%{filter:brightness(.3)}100%{filter:brightness(1)}}",
        f"#curtain{{animation:wipe {T_WIPE}s steps(40,end) {T_CUT}s 1 both}}",
        "@keyframes wipe{0%{transform:translate(0)}100%{transform:translate(160px)}}",
        "#clouds{animation:drift 40s steps(160,end) infinite}",
        "@keyframes drift{0%{transform:translate(0)}100%{transform:translate(-160px)}}",
    ]
    for lid, delay, dy, dur in (("shades", T_SHADES, -34, 0.6),
                                ("shirt", T_SHIRT, 16, 0.6),
                                ("hat", T_HAT, -46, 0.7)):
        kf = f"drop-{lid}"
        out.append(f"#{lid}{{animation:{kf} {dur}s steps(5,end) {delay}s 1 both}}")
        out.append(f"@keyframes {kf}{{0%{{transform:translate(0,{dy}px);opacity:0}}"
                   f"1%{{opacity:1}}100%{{transform:translate(0);opacity:1}}}}")
    for pre, n, period in FRAME_SETS:
        kf = f"cyc{n}"
        for i in range(n):
            out.append(f"#{pre}-{i}{{animation:{kf} {period}s steps(1,end) "
                       f"{i * period / n:.3f}s infinite}}")
        share = 100.0 / n
        out.append(f"@keyframes {kf}{{0%,{share - 0.01:.2f}%{{opacity:1}}"
                   f"{share:.2f}%,100%{{opacity:0}}}}")
    return "".join(out)


def group(sc, name):
    return f'<g id="{name}">{emit(merge(sc.layers[name]))}</g>' if name in sc.layers else ""


def render(sc, scale, animate=True, frame=None):
    bg = "".join(group(sc, n) for n in BG)
    fig = "".join(group(sc, n) for n in FIGURE)
    style = f"<style>{css()}</style>" if animate else ""
    curtain = f'<rect id="curtain" width="{W}" height="{H}" fill="#000"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W*scale}" height="{H*scale}" shape-rendering="crispEdges" '
            f'role="img" aria-label="8-bit chrome endoskeleton on Venice Beach">'
            f'{style}<rect width="{W}" height="{H}" fill="#000"/>{bg}{curtain}'
            f'<g id="figure">{fig}</g></svg>')


def build_scene():
    sc = Scene()
    sky(sc); clouds(sc); sea(sc); rollers(sc); beach(sc); shore_foam(sc)
    palms(sc); figure(sc)
    return sc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sprite", help="preview one art/*.txt sprite in isolation")
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--scale", type=int, default=6)
    p.add_argument("--static", action="store_true", help="drop the CSS timeline")
    a = p.parse_args()

    if a.sprite:
        g = Grid.load(a.sprite, a.mirror)
        rs = g.rects()
        print(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {g.w} {g.h}" '
              f'width="{g.w*a.scale}" height="{g.h*a.scale}" shape-rendering="crispEdges">'
              f'<rect width="100%" height="100%" fill="#202028"/>{emit(rs)}</svg>', end="")
        print(f"{a.sprite}: {g.w}x{g.h}, {len(rs)} rects", file=sys.stderr)
        return

    sc = build_scene()
    out = render(sc, a.scale, animate=not a.static)
    print(out, end="")
    merged = sum(len(merge(v)) for v in sc.layers.values())
    print(f"{merged} rects after merge, {len(out)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
