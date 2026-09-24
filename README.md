# Spun, Not Drawn

## Thesis

A spider web is not a shape. It is the fossil of a behaviour. Each record in a specimen preserves one step of a spider's thread-laying itinerary; later phases will build and render the nine Australian spiders and their webs.

![The garden orb at dusk](renders/hortophora_dusk.png)

## Algorithms

The reference garden orb is constructed by a spider navigating a plan graph. Twigs appear first; she walks their existing edges, bridges two upper anchors, spins a Y to the hub and lower anchor, closes the frame, adds radii in the largest angular gaps, weaves three hub rings, lays a temporary outward spiral, then lays an inward sticky spiral. A radius candidate is jittered about its gap midpoint and rejected if either new gap would be under 0.45 times the mean. Each spiral chord updates its spoke's frontier; unavailable neighbours cause an actual reversal, never a scripted one. An inward row can take a shortened final step to just outside the free zone rather than leave a missing sector. As the capture frontier passes each temporary chord, both of its attachment frontiers must be at least half a capture spacing inward before the chord is eaten.

The graph records every eventual junction before emission. Later attachments split graph edges, not emitted records. Replay emits each thread already split at all its future nodes, and each walk retraces exactly one live sub-record at a time. Quantizing each node only once keeps the spider's steps and attached thread endpoints bit-identical.

Tension-only relaxation sets each spring's rest length to `(1 − ε) × planned length`; frame, radius, capture and hub springs use the kind-specific ε and stiffness in the construction brief. At each iteration, `v ← 0.85 × (v + 0.2F)` and `x ← x + 0.2v`; anchors stay fixed. Displacement, junction order and newly introduced crossings are checked before accepting the result. Pacing uses `length/speed + dwell` per record, compresses environmental time to at most 8%, integrates the specified four-knot ease-speed curve, and samples 512 fractional cursors at uniform presentation times.

## The `.silk` format

Version 1 is little-endian. A 32-byte header (`<4sHHHHIIHHHBBB3x`) holds magic `SILK`, version `1`, header/record/bead sizes `32/20/8`, segment and bead counts (u32), canvas width and height (u16), coordinate scale `4` (u16), width scale `32` (u8), zero flags (u8), builder count `1–3` (u8), and three zero reserved bytes. The first record starts at byte 32; beads directly follow the records. Files must end immediately after the beads.

Each 20-byte record (`<4HI8B`) stores x0, y0, x1, y1 in canvas pixels ×4 (u16); its removal index (u32, or `0xFFFFFFFF` if permanent); and eight bytes in this order: kind, width (pixels ×32), red, green, blue, LOD, flags, alpha. Flag bits 0, 1 and 2 mean sticky, environment and invisible; bits 4–5 select the builder. Records are emitted in construction order and never changed by replay.

Each 8-byte bead (`<IHBB`) stores its host record index (u32), fraction along that host ×65535 (u16), radius in pixels ×16 (u8), and flags (u8). Bead flag bits 0, 1 and 2 mean satellite, glue and lure. In-memory NumPy structured dtypes use these exact layouts, so serialization writes header + records.tobytes() + beads.tobytes() without per-record repacking. Coordinates, widths and bead sizes use nearest-even rounding at the stated scales.

## Rendering architecture

The current reference dusk plate composites silk in record order using actual source-over alpha, with environmental twigs below silk. Lines use the viewer's hairline coverage rule: `w = max(record_width, 0.55)` pixels, drawn diameter `max(w, 1)` pixels, and alpha multiplied by `min(w, 1)`. The renderer draws at 4× canvas size, downsamples with Lanczos, adds a radius-14 Gaussian of the silk layer at strength 0.5, then composites the sharp layers.

## Decisions

- The checkout directory itself is the project root; the Python package is its direct child `spun/`.
- Header version, sizes, scales, reserved bytes and file length are checked when decoding. The validator maps malformed files to Rule 1 and reports Rules 1–9 by number. Rule 10's byte-identical consecutive-build check belongs with the build tool.
- Validator metadata holds specimen kind, one hub/frame polygon and radial endpoints per orb builder, open-sector angular intervals, the golden flag, 512 timeline cursors, stage boundaries, per-builder spinneret rest positions, and catalogue/index/default asset byte totals. Geometry and rest positions are checked against decoded, quantized records rather than trusting claims of validity in metadata.
- Geometric limits use inclusive CV bounds. The validator reconstructs each possibly kinked radial spoke from decoded radius records; capture endpoints must match actual radial nodes exactly, and spoke drift is bounded by the relaxation displacement allowance plus half a native pixel. Budget KB/MB are interpreted as KiB/MiB.
- The 512-sample pacing module moved forward to Phase 2 so the actual reference itinerary can pass Rule 8. If relaxation violates the displacement, radial-order, crossing or quantized-length conditions, the deterministic fallback is the unchanged planned coordinates.
- Spiral jump targets are only spokes from which a chord can actually leave (so an isolated frontier cannot induce an endless walk). Remaining temporary silk is removed before the final walk. Future open sectors are removed from the angular gaps before proposing new radii.
- Row-laying "no room" also covers level: an inward row refuses an already-visited neighbour whose candidate junction lies deeper than her own junction by more than `max(s, 0.5·d·Δθ)` (the chord would run nearly radial). She turns back, so spokes with more remaining room gain extra rows until the rows are level again. This is what makes golden's lower-half turnbacks, and the concentric rows round every hub, emerge instead of fans of near-radial chords.
- A new spiral junction closer than 1 px to an existing node on the same spoke reuses that node: sub-pixel radial stubs quantize into false crossings (golden retains its temporary spiral, so capture and temporary junctions meet on the same spokes).
- Golden: temporary spiral kept at alpha 0.32 in `#b89a55`. Barrier: 52–66 points in a 170×820×220 px box between the right frame and the right branch, obliquely projected (x += 0.32z, y += 0.12z); a nearest-edge spanning tree (so she always walks on silk) plus 2–3 nearest partners per point, and three long stays to frame anchors; alpha 0.35–0.6 from depth. Golden radii 38–46 and capture 7.4→6.3 px (within ±30%) keep records under 19,000 for the Phase 5 bead budget.
- Specimen `bounds` (Phase 5) will cover every non-INVISIBLE record, ENV included, plus the rest-glyph extent: the viewer clips its per-instance buffers to them.
- Scaffold branches have a separate deterministic random stream from frame, radii and spiral construction, so editing bark and leaf geometry cannot silently change the orb topology. Spiral first visits use their actual initial radii rather than consuming a spacing step; the capture shimmer is perpendicular to the upper-left light.
- Icon generation moves to Phase 5: `tools/icons.py` will produce favicon, Apple touch and manifest icons under `web/icons/`, ahead of the viewer's cold-load checks.

### Viewer

- Canvas2D: an append-only permanent layer (completed never-dying records and their glue beads, each stroked once) plus a dynamic layer redrawn only when the cursor moves (live/fading temporaries and the tip). Temporaries therefore draw above permanent silk; this z-order difference is accepted. Layer buffers are snapped to whole device pixels so they composite without resampling. If Canvas2D filter blur is unavailable, glow is skipped without affecting the sharp silk.
- WebGL2: the record VBO is the `.silk` record bytes uploaded once per specimen; glue beads use one resolved VBO per specimen. While webs grow only uniforms change. Sharp silk is drawn into a full-resolution FBO, then box-downsampled to half resolution. The Canvas2D blur σ (radius·0.5·dpr half-res px) is matched by n ≥ 2 passes per axis of a 13-sample bilinear-paired Gaussian with σ/√n, where n = max(2, ⌈(2.4σ/12)²⌉) keeps every pass within ±12 texels at 2.4σ. The backend defaults to GL when WebGL2 exists and persists in `localStorage["spun-backend"]`.
- Placement: the specimen anchor stays under the pointer; each side's overshoot of the 4 px stage inset shrinks the web independently, down to a floor of 0.12 × the ideal scale. Only when the floor still cannot fit is the anchor shifted by the minimum per-axis amount needed for the inset. Detail = scale / ideal scale drives the LOD threshold.
- Compositing order (2D, GL and Python plates alike): background → sharp silk (source-over, chronological) → glow added with `lighter` at the glow strength (×1.2 in Dawn). The 2D canvas paints the background itself each frame; each instance's half-resolution glow buffer is padded by ⌈3σ⌉ on every side so the halo is not clipped.
- Hairlines: device width w_px = max(w·s, 0.55)·dpr; the stroke diameter is max(w_px, 1) device px and alpha is multiplied by min(w_px, 1).
- `temporary` holds exactly the records with a death index; never-dying auxiliary silk joins the append-only permanent layer.

## Plate notes

**Hortophora transmarina.** Earlier plates read as a near-regular decagon with a centred hub and nested regular rows. The frame now has ten anchors at irregular 29°–52° spacings and ±17% distances (a tall oval, deepest below), hub at 0.40 of the frame height, on three curved boughs (top, right, left) instead of a box of four; rows now bend round the hub and turnbacks sit where the frame is deep.

**Trichonephila edulis.** First plate: bright fans of near-radial chords below the hub (constant row offsets inherited from the 0.94·R start), hub pushed far left, barrier a thin zig-zag chain. Fixes: the level rule above (rows become concentric near the hub and turn back in the deep lower half), the bridge re-centred over the orb, and a wider deeper barrier box that reads as a mesh curtain between the orb and the right-hand trunk. The retained temporary spiral shows as faint darker-gold rows.

**Argiope keyserlingi.** First plate shared the others' four-branch box and a regular decagon. Now one arching stem wraps the web on the left and top and a second curls in from the right and below, the frame is a skewed decagon, and four `#f6f9ff` zig-zag bands run r_h1+6 → 0.55·R_k on the diagonal radii, so the cross is lopsided the way real ones are.
