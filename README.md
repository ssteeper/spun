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
- Frame corners come from the scaffold (`frame_polygon(branches)`): a corner within 12 px of a branch sits on the bark; otherwise a short, nearly straight tapering side twig (≤ 90 px, one gentle bend, some forked) carries it. The earlier S-shaped connector twigs read as wires and are gone. Each species has its own set piece (golden: leaning sapling + crown bough + ground limb; argiope: one arching stem + a cross stem; hortophora: a three-stemmed shrub; phonognatha: a forked sapling under a crossing twig; austracantha: a U-fork flanked by two bushes; arachnura: two stems meeting in a V under a level twig).
- A spiral junction reached by a jump counts as that spoke's first visit (otherwise a later row could re-lay the identical chord backwards).
- Rule 6's radial-gap CV skips the gaps bordering an open sector (Arachnura's V is signature, not jitter); the same filter is used for reported metrics.
- Colony: each later orb lists `shared` frame corners; they are attached to an earlier orb's live frame thread (pre-split in the plan graph) before she starts. Orb RNG seeds come from `christmas-jewel-spider`, `-2`, `-3`. Tufts are half-ellipse loops from one frame knot out and back to a second knot 2–3 px along, 6–10 segments fitted to 6–12 px, every 20 mm/0.35 = 57 px (×U[0.75, 1.25]); after relaxation their interior follows the mean shift of the two knots.
- Phonognatha's leaf is emitted as LEAF/ENV records after the capture spiral (stage "hauling a leaf"), then 8 RETREAT stitches bind it to radii; free zone 72 px (+29%) so the leaf sits in a clearer hub.
- Every result's metadata carries `anchor` (the hub; the centre web's hub for the colony) and `mmPerUnit`.
- Icon generation moves to Phase 5: `tools/icons.py` will produce favicon, Apple touch and manifest icons under `web/icons/`, ahead of the viewer's cold-load checks.

### Viewer

- Canvas2D: an append-only permanent layer (completed never-dying records and their glue beads, each stroked once) plus a dynamic layer redrawn only when the cursor moves (live/fading temporaries and the tip). Temporaries therefore draw above permanent silk; this z-order difference is accepted. Layer buffers are snapped to whole device pixels so they composite without resampling. If Canvas2D filter blur is unavailable, glow is skipped without affecting the sharp silk.
- WebGL2: the record VBO is the `.silk` record bytes uploaded once per specimen; glue beads use one resolved VBO per specimen. While webs grow only uniforms change. Sharp silk is drawn into a full-resolution FBO, then box-downsampled to half resolution. The Canvas2D blur σ (radius·0.5·dpr half-res px) is matched by n ≥ 2 passes per axis of a 13-sample bilinear-paired Gaussian with σ/√n, where n = max(2, ⌈(2.4σ/12)²⌉) keeps every pass within ±12 texels at 2.4σ. The backend defaults to GL when WebGL2 exists and persists in `localStorage["spun-backend"]`.
- Placement: the specimen anchor stays under the pointer; each side's overshoot of the 4 px stage inset shrinks the web independently, down to a floor of 0.12 × the ideal scale. Only when the floor still cannot fit is the anchor shifted by the minimum per-axis amount needed for the inset. Detail = scale / ideal scale drives the LOD threshold.
- Compositing order (2D, GL and Python plates alike): background → sharp silk (source-over, chronological) → glow added with `lighter` at the glow strength (×1.2 in Dawn). The 2D canvas paints the background itself each frame; each instance's half-resolution glow buffer is padded by ⌈3σ⌉ on every side so the halo is not clipped.
- Dawn: dew (non-GLUE beads) shows only in Dawn and only on completed webs. Each web's dew clock starts at the later of its completion and the moment Dawn was switched on, on the virtual clock (so `seek` works). Bead i starts at 2.4 s·u_i (u_i = hash32(i)/2³²) and grows over 0.35 s with an ease-out cubic. A web keeps ticking until 2.75 s after its origin, then stops. Canvas2D bakes fully grown dew into a per-instance dew layer and draws growing dew in the dynamic layer. GL keeps u_i in the bead VBO and tests dew visibility per instance from uniforms. Switching to Dusk clears dew; dew is hidden when detail < 0.35. Glow strength ×1.2 applies stage-wide in Dawn.
- Offline: `sw.js` cache names embed `VERSION`, and old `spun-*` caches are deleted on activate. Install precaches the shell (HTML, CSS, every JS module, the manifest, `offline.html`, favicon and Apple touch icon), `index.json` and the default specimen's `.silk`. `.silk` is cache-first and filled on demand; `index.json` is stale-while-revalidate. Navigations are network-first; offline they fall back to the cached `index.html`, or to `offline.html` when `index.json` is not cached. `?nosw=1` skips registration and unregisters existing workers.
- Hairlines: device width w_px = max(w·s, 0.55)·dpr; the stroke diameter is max(w_px, 1) device px and alpha is multiplied by min(w_px, 1).
- `temporary` holds exactly the records with a death index; never-dying auxiliary silk joins the append-only permanent layer.

## Plate notes

**Hortophora transmarina.** Earlier plates read as a near-regular decagon with a centred hub and hung from wavy connector twigs. Now: ten irregular anchors (29°–52°, ±17%) on a three-stemmed shrub, corners on bark or short straight twigs, hub at 0.40; rows bend round the hub, turnbacks where the frame is deep.

**Trichonephila edulis.** First plate: bright fans of near-radial chords below the hub and a thin barrier chain. Fixes: the level rule (concentric rows near the hub, 117 emergent turnbacks filling the deep lower half), a sapling-and-crown-bough frame, and the barrier moved beyond the right limb as a mesh curtain. Dim retained temporary rows show as darker gold. Small fans remain at the two lower corners.

**Argiope keyserlingi.** Moved off the shared four-branch box: one stem arches over the left and top, a cross stem curls under the right. Four `#f6f9ff` zig-zag bands on the diagonal radii make a lopsided X.

**Phonognatha graeffei.** First plate: the rolled leaf was a faint thin sliver lost in the mesh. Revised: broader leaf (146 px) with six nested curl outlines, midrib and seven vein pairs, mouth down at the hub, eight pale stitches to radii, a wider free zone; she rests at the mouth.

**Austracantha minax.** Three small orbs, built in turn, in a U-fork with a bush on each side; the side orbs tie one corner onto the centre orb's frame. White tufts every ~20 mm line all three frames (first render: tufts overshot 12 px after relaxation, now fitted and carried with the frame).

**Arachnura higginsi.** First plate: egg sacs were circles set off alternately to each side of the signal line. Revised: seven ovals hung along the line itself with slanted woolly hatching, the spider at the bottom; the upward V (28° half-angle) is empty except for the signal line, rows turn back at its edges.
