"""One-shot: outline the glyphs of a title string into SVG path data.

Run in a throwaway venv. The output gets committed, so the repo itself needs
no font files and no fontTools at build time, and the type renders identically
for every viewer regardless of what fonts they have.
"""
import json, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform

FONT = "/System/Library/Fonts/Supplemental/Impact.ttf"
TEXT = sys.argv[1] if len(sys.argv) > 1 else "MAX'S GIT PAGE"
CAP = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0   # target cap height
TRACK = float(sys.argv[3]) if len(sys.argv) > 3 else -0.02  # em of extra tracking

f = TTFont(FONT)
upm = f["head"].unitsPerEm
cmap = f.getBestCmap()
gs = f.getGlyphSet()
cap_h = f["OS/2"].sCapHeight if hasattr(f["OS/2"], "sCapHeight") else upm * 0.7
scale = CAP / cap_h

print(f"{f['name'].getDebugName(4)}  upm={upm} capHeight={cap_h} "
      f"scale={scale:.4f}", file=sys.stderr)

glyphs, x = [], 0.0
for ch in TEXT:
    name = cmap.get(ord(ch))
    if name is None:
        raise SystemExit(f"glyph missing for {ch!r}")
    g = gs[name]
    if ch != " ":
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}")
        # flip y (font units go up, SVG down) and land the baseline at y=0
        g.draw(TransformPen(pen, Transform(scale, 0, 0, -scale, x, 0)))
        d = pen.getCommands()
        if d:
            glyphs.append({"ch": ch, "d": d})
    x += g.width * scale + CAP * TRACK

out = {"font": f["name"].getDebugName(4), "text": TEXT,
       "cap": CAP, "advance": round(x, 2), "glyphs": glyphs}
json.dump(out, open("title-glyphs.json", "w"), indent=1)
print(f"{len(glyphs)} glyphs, total advance {x:.1f} units", file=sys.stderr)
