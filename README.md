<div align="center">

<img src="./venice-beach.svg" alt="Animated 8-bit Venice Beach: swaying palms, rolling surf and drifting clouds" width="100%" />

# :sunglasses:  Max's Git Page  :sunglasses:

</div>

<br>

---

<details>
<summary><sub>how the animation works</sub></summary>

<br>

`venice-beach.svg` is generated, not hand-written. Run `python3 build.py > venice-beach.svg`.

**Fully procedural.** There are no sprite files — the scene is pure geometry, drawn by
`build.py` from a 20-colour `palette.json`. A 160×20 pixel grid in a `viewBox`, so it
stays crisp at any width. Adjacent same-colour pixels are run-length merged into single
`<rect>`s, which also resolves overdraw. 473 rects, 23 KB.

**Nothing plays once.** Every animation is an infinite loop, so the banner never settles:

| Element | Frames | Period |
|---|---|---|
| Palm fronds, near tree | 4 | 2s |
| Palm fronds, far tree | 4 | 2.5s |
| Ocean crests | 4 | 1.5s |
| Shoreline foam | 4 | 3.1s |
| Cloud drift | scrolled | 1.5s |

Periods are deliberately non-harmonic. Shared factors would make the whole scene visibly
pulse in unison every few seconds.

**Animation is pure CSS.** GitHub serves README images through a proxy and renders them
in an `<img>`, so JavaScript never runs — only CSS and SMIL do. Every loop uses `steps()`
timing to swap discrete frames, because interpolating pixel art puts pixels on
half-coordinates and blurs the grid. The one continuous motion, the cloud scroll, is
quantised with `steps(160)` so it advances exactly one grid pixel at a time, and the
cloud layer is tiled to twice the canvas width so the wrap is seamless.

**Palm fronds** are sampled quadratic Bézier spines with thickness tapering from base to
tip. Advancing one column per iteration and drawing vertical runs instead merges the
blades into a flat mushroom cap. Swapping a `wind` offset across four frames animates the
sway, and the offsets run back and forth (`-2, 0, +2, 0`) so the loop never snaps.

**Checks.** `python3 test_build.py` verifies the palette is exact with no dead entries,
the SVG parses, every `#id` the CSS animates exists, every animation is `infinite`, and
no layer paints off-canvas. That last one is not theoretical — it caught a palm crown
whose top frond was being clipped by the viewBox. None of them assert the art looks
right; that is settled by rendering it and looking.

**Tweaking.** Colours are all in `palette.json`. Geometry is constants near the top of
`build.py`: `W`/`H` for the canvas, `HORIZON`/`SHORE`/`SAND` for the bands, `TREES` for
palm placement.

</details>
