#!/usr/bin/env python3
"""Build the animated 8-bit Venice Beach endoskeleton banner.

Art comes from two places:
  art/*.txt   ASCII grids, one char per pixel, '.' transparent. Used where
              every pixel matters (head, shades, fedora).
  Scene.*     procedural primitives. Used for geometry (sky, sea, sand,
              palms, shoulders, shirt) where hand-typing a grid is silly.

Chars map to hex via palette.json. Output is a 160x45 letterbox: the head
fills the height, the beach sits in the side thirds.
"""
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).parent
ART = ROOT / "art"
PALETTE = {k: v for k, v in json.loads((ROOT / "palette.json").read_text()).items()
           if not k.startswith("_")}

W, H = 160, 45
HORIZON, SHORE, SAND = 17, 25, 29
HEAD_X, HEAD_Y = 63, 2
FACE_CX = 80


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
        missing = {c for r in g.rows for c in r if c != "."} - set(PALETTE)
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
        for dy in range(-r, r + 1):
            half = int((r * r - dy * dy) ** 0.5)
            self.box(name, cx - half, cy + dy, half * 2 + 1, 1, c)


# ---------------------------------------------------------------- sky and sea

def dither(sc, name, y, c, phase=0):
    """50% checkerboard: the classic 8-bit band blend. Sparser stipples read
    as dotted lines rather than a gradient."""
    for x in range(phase, W, 2):
        sc.px(name, x, y, c)


SKY_RAMP = (("1", 5), ("A", 4), ("2", 3), ("B", 2), ("3", 2), ("C", 1))


def sky(sc):
    y = 0
    for c, hh in SKY_RAMP:
        sc.box("sky", 0, y, W, hh, c)
        y += hh
    prev = None
    for i, (c, hh) in enumerate(SKY_RAMP):
        if prev and hh >= 3:
            dither(sc, "sky", sum(h for _, h in SKY_RAMP[:i]), prev, i % 2)
        prev = c
    sc.disc("sky", 118, 5, 4, "y")
    sc.disc("sky", 118, 5, 3, "o")


CLOUD_SHAPES = {"s": ((2, 4), (0, 8), (1, 6)),
                "m": ((3, 7), (0, 13), (2, 10))}


def cloud(sc, x, y, kind):
    rows = CLOUD_SHAPES[kind]
    for i, (dx, ww) in enumerate(rows):
        sc.box("clouds", x + dx, y + i, ww, 1, "p" if i == len(rows) - 1 else "o")


def clouds(sc):
    for ox in (0, W):                      # tiled to 2W so a -W scroll wraps
        cloud(sc, ox + 8, 2, "m")
        cloud(sc, ox + 44, 1, "s")
        cloud(sc, ox + 104, 3, "m")
        cloud(sc, ox + 132, 1, "s")


def sea(sc):
    for y0, y1, c in ((HORIZON, 19, "5"), (19, 22, "6"), (22, SHORE, "7")):
        sc.box("sea", 0, y0, W, y1 - y0, c)
    sc.box("sea", 0, HORIZON, W, 1, "8")   # crisp horizon glint


ROLLER_FRAMES = FOAM_FRAMES = 4


def rollers(sc):
    """Dashed foam crests creeping shoreward; the phase reset reads as a break."""
    for f in range(ROLLER_FRAMES):
        for j, base in enumerate((18, 20, 21)):
            y, dash, gap = base + f, 6 + j * 2, 11 + j * 3
            x = -((f * 5 + j * 7) % (dash + gap))
            while x < W:
                if x + dash > 0:
                    sc.box(f"roller-{f}", max(0, x), y,
                           min(dash, W - max(0, x)), 1, "8")
                x += dash + gap


def shore_foam(sc):
    """The waterline runs up the wet sand and slides back."""
    for f in range(FOAM_FRAMES):
        adv = (0, 2, 3, 1)[f]
        sc.box(f"foam-{f}", 0, SHORE - 1 + adv, W, 2, "8")
        for x in range(0, W, 9):
            sc.px(f"foam-{f}", (x + f * 4) % W, SHORE + 1 + adv, "8")


def beach(sc):
    sc.box("sand", 0, SHORE, W, SAND - SHORE, "c")
    sc.box("sand", 0, SAND, W, H - SAND, "s")
    seed = 0x9E3779B9
    for _ in range(70):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = (seed >> 7) % W
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = SAND + 1 + (seed >> 11) % (H - SAND - 1)
        sc.px("sand", x, y, "b" if (seed >> 3) % 3 else "a")


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
    """One blade: a Bezier spine with thickness tapering base -> tip."""
    p1 = (cx + ctrl[0] * scale, cy + ctrl[1] * scale)
    p2 = (cx + end[0] * scale, cy + end[1] * scale)
    for x, y, t in bezier((cx, cy), p1, p2):
        thick = 3 if t < 0.45 else 2 if t < 0.8 else 1
        sc.box(name, x, y - thick // 2, 1, thick, "g")
        sc.px(name, x, y - thick // 2, "h")
        if thick > 1:
            sc.px(name, x, y - thick // 2 + thick - 1, "i")


FRONDS = (((-17, 9), (-12, -8)), ((-14, 3), (-9, -9)), ((-8, -7), (-6, -10)),
          ((0, -11), (1, -10)),
          ((8, -7), (6, -10)), ((14, 3), (9, -9)), ((17, 9), (12, -8)))
PALM_WIND = (-2.0, 0.0, 2.0, 0.0)          # back and forth: the loop never snaps
TREES = (("palm-far", 141, 33, 18, 0.5, 0.62),
         ("palm-near", 15, 39, 24, -0.4, 0.8))


def palm_trunk(sc, name, bx, by, height, lean):
    for i in range(height):
        y, t = by - i, i / (height - 1)
        x = bx + round(lean * t * t * 8)
        wide = 3 if t < 0.4 else 2
        sc.box(name, x, y, wide, 1, "t")
        sc.px(name, x if lean > 0 else x + wide - 1, y, "u")


def palm_crown(sc, name, bx, by, height, lean, scale, wind):
    """wind bends every blade downwind; swapping wind values animates the sway."""
    cx, cy = bx + round(lean * 8) + 1, by - height
    for end, ctrl in FRONDS:
        frond(sc, name, cx, cy,
              (end[0] + wind, end[1] + abs(wind) * 0.4),
              (ctrl[0] + wind * 0.5, ctrl[1] + abs(wind) * 0.3), scale)
    sc.box(name, cx - 1, cy - 1, 3, 2, "i")


def palms(sc):
    for name, bx, by, h, lean, scale in TREES:
        palm_trunk(sc, f"{name}-trunk", bx, by, h, lean)
        for f, wind in enumerate(PALM_WIND):
            palm_crown(sc, f"{name}-{f}", bx, by, h, lean, scale, wind)


# ---------------------------------------------------------------- figure
# Shoulders and shirt share ONE half-width profile, so the shirt can never
# drift off the body. Index 0 sits at the base of the neck.
TORSO = (10, 18, 26, 30, 32, 32, 32, 32, 32)
TORSO_Y = 36


def neck_cut(i):
    """Half-width of the open collar at torso row i. Reaches 0 so the V has a
    point and the last two rows can carry a button placket."""
    return (9, 7, 5, 3, 2, 1, 0, 0, 0)[i]


def shoulders(sc):
    """Bare chrome, visible only between the wipe and the shirt landing."""
    for i, hw in enumerate(TORSO):
        y = TORSO_Y + i
        if y >= H:
            break
        for d in range(hw):
            c = "K" if d == 0 else "D" if d < 3 else "M"
            sc.px("torso", FACE_CX - hw + d, y, c)
            sc.px("torso", FACE_CX + hw - 1 - d, y, c)


FLOWERS = ((-26, 5, "n"), (-19, 7, "v"), (-12, 5, "n"), (-6, 8, "v"),
           (5, 5, "n"), (11, 8, "n"), (18, 5, "v"), (25, 7, "n"),
           (-23, 8, "v"), (22, 3, "n"), (-15, 3, "v"), (14, 3, "n"))


def shirt(sc):
    """Hawaiian, not a straitjacket: separated sleeves, real lapels, floral.
    Four visible rows, so lapel shape and print do all the talking."""
    for i, hw in enumerate(TORSO):
        y = TORSO_Y + i
        if y >= H:
            break
        cut = neck_cut(i)
        for d in range(hw):
            for x in (FACE_CX - hw + d, FACE_CX + hw - 1 - d):
                off = abs(x - FACE_CX)
                if off < cut:
                    continue                       # collar stays open
                if d == 0 or (cut and off in (cut, cut + 1)):
                    c = "w"                        # hem edge and lapel fold
                elif d == 6 and hw > 22:
                    c = "w"                        # sleeve seam
                elif cut == 0 and off in (1, 2):
                    c = "w"                        # button placket
                else:
                    c = "f"
                sc.px("shirt", x, y, c)
    for dx, i, c in FLOWERS:
        y = TORSO_Y + i
        if y < H and abs(dx) >= neck_cut(i):
            sc.px("shirt", FACE_CX + dx, y, c)
            sc.px("shirt", FACE_CX + dx, y - 1, "y" if c == "n" else "v")


def figure(sc):
    shoulders(sc)
    # the optic has to animate independently, so split it off the head
    for x, y, w, h, c in Grid.load("head", mirror=True).rects(HEAD_X, HEAD_Y):
        if c == "R":
            sc.add("optic-0", [(x, y, w, h, c)])
            sc.add("optic-1", [(x, y, w, h, "G")])
        else:
            sc.add("head", [(x, y, w, h, c)])
    shirt(sc)
    sc.sprite("shades", Grid.load("shades"), 64, 16)
    sc.sprite("hat", Grid.load("fedora", mirror=True), 58, 0)


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


# ---- timeline (seconds). One-shots run once and hold; ambient loops forever.
T_CUT, T_WIPE = 2.0, 2.0
T_SHADES, T_SHIRT, T_HAT = 4.0, 5.5, 7.0

FRAME_SETS = [("palm-near", len(PALM_WIND), 1.2),
              ("palm-far", len(PALM_WIND), 1.5),   # not 1.2: no lockstep sway
              ("roller", ROLLER_FRAMES, 0.5),
              ("foam", FOAM_FRAMES, 3.1),
              ("optic", 2, 1.8)]

BG = (["sky", "clouds", "sea"]
      + [f"roller-{f}" for f in range(ROLLER_FRAMES)] + ["sand"]
      + [f"foam-{f}" for f in range(FOAM_FRAMES)]
      + ["palm-far-trunk"] + [f"palm-far-{f}" for f in range(len(PALM_WIND))]
      + ["palm-near-trunk"] + [f"palm-near-{f}" for f in range(len(PALM_WIND))])
FIGURE = ["torso", "shirt", "head", "optic-0", "optic-1", "shades", "hat"]


def css():
    frame_ids = [f"{p}-{i}" for p, n, _ in FRAME_SETS for i in range(n)]
    out = [",".join(f"#{i}" for i in frame_ids) + "{opacity:0}",
           # 2x -> 1x in one hard jump: only integer factors keep the pixel
           # grid, and 8-bit games cut rather than zoom
           "#figure{transform-box:view-box;transform-origin:80px 18px;"
           f"animation:zoomcut {T_CUT}s steps(1,end) 0s 1 both,"
           f"lightup 1s steps(3,end) {T_CUT}s 1 both}}",
           "@keyframes zoomcut{0%{transform:scale(2)}100%{transform:scale(1)}}",
           "@keyframes lightup{0%{filter:brightness(.45)}100%{filter:brightness(1)}}",
           f"#curtain{{animation:wipe {T_WIPE}s steps(40,end) {T_CUT}s 1 both}}",
           "@keyframes wipe{0%{transform:translate(0)}100%{transform:translate(160px)}}",
           "#clouds{animation:drift 40s steps(160,end) infinite}",
           "@keyframes drift{0%{transform:translate(0)}100%{transform:translate(-160px)}}"]
    for lid, delay, dy, dur in (("shades", T_SHADES, -22, 0.6),
                                ("shirt", T_SHIRT, 10, 0.6),
                                ("hat", T_HAT, -30, 0.7)):
        out.append(f"#{lid}{{animation:drop-{lid} {dur}s steps(5,end) {delay}s 1 both}}")
        out.append(f"@keyframes drop-{lid}{{0%{{transform:translate(0,{dy}px);opacity:0}}"
                   f"1%{{opacity:1}}100%{{transform:translate(0);opacity:1}}}}")
    for pre, n, period in FRAME_SETS:
        for i in range(n):
            out.append(f"#{pre}-{i}{{animation:cyc{n} {period}s steps(1,end) "
                       f"{i * period / n:.3f}s infinite}}")
        share = 100.0 / n
        out.append(f"@keyframes cyc{n}{{0%,{share - 0.01:.2f}%{{opacity:1}}"
                   f"{share:.2f}%,100%{{opacity:0}}}}")
    return "".join(out)


def render(sc, scale, animate=True):
    def group(n):
        return f'<g id="{n}">{emit(merge(sc.layers[n]))}</g>' if n in sc.layers else ""
    bg = "".join(group(n) for n in BG)
    fig = "".join(group(n) for n in FIGURE)
    style = f"<style>{css()}</style>" if animate else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W*scale}" height="{H*scale}" shape-rendering="crispEdges" '
            f'role="img" aria-label="8-bit endoskeleton acquiring beachwear on '
            f'Venice Beach">{style}<rect width="{W}" height="{H}" fill="#05070d"/>'
            f'{bg}<rect id="curtain" width="{W}" height="{H}" fill="#05070d"/>'
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
    print(f"{sum(len(merge(v)) for v in sc.layers.values())} rects after merge, "
          f"{len(out)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
