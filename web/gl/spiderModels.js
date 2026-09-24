// 3-D anatomy for the ray-marched spiders. Sizes and colours come from each glyph in index.json
// (authored in millimetres from the spinnerets, heading +x, the spider's left toward -y); this
// table adds what a flat glyph cannot say: body depth, pattern, eye layout and species features.

export const PATTERN = Object.freeze({
  golden: 0, argiope: 1, garden: 2, leafCurler: 3, jewel: 4, scorpionTail: 5, netCaster: 6, magnificent: 7, redback: 8,
});

export const EYES = Object.freeze({ araneid: 0, deinopid: 1, theridiid: 2 });

// depth: abdomen height as a fraction of its half-width; carDepth likewise for the carapace.
// gloss: specular strength of the cuticle; hair: how furry the legs look; tissue: colour of light
// passing through the abdomen when backlit.
export const MODELS = Object.freeze({
  "golden-orb-weaver": { L: 30, pattern: PATTERN.golden, eyes: EYES.araneid, depth: 0.82, carDepth: 0.55, gloss: 0.55, hair: 0.8, tissue: "#d8c68a", accent: "#f3efe0", legTips: "#2c2621", legBandAt: "knee" },
  "st-andrews-cross": { L: 15, pattern: PATTERN.argiope, eyes: EYES.araneid, depth: 0.62, carDepth: 0.5, gloss: 0.65, hair: 0.45, tissue: "#f0d676", accent: "#f4f6f8", legTips: "#3a3632", legBandAt: "stripes" },
  "garden-orb-weaver": { L: 22, pattern: PATTERN.garden, eyes: EYES.araneid, depth: 0.95, carDepth: 0.6, gloss: 0.35, hair: 0.9, tissue: "#b98552", accent: "#c7ab82", legTips: "#4a3a2c", legBandAt: "rings" },
  "leaf-curling-spider": { L: 12, pattern: PATTERN.leafCurler, eyes: EYES.araneid, depth: 0.8, carDepth: 0.55, gloss: 0.45, hair: 0.6, tissue: "#c7a06a", accent: "#c9ab7c", legTips: "#5a4630", legBandAt: "none" },
  "christmas-jewel-spider": { L: 8, pattern: PATTERN.jewel, eyes: EYES.araneid, depth: 0.55, carDepth: 0.5, gloss: 0.9, hair: 0.2, tissue: "#6b5a3a", translucency: 0.15, accent: "#f2ebd5", legTips: "#26262a", legBandAt: "stripes" },
  "scorpion-tailed-spider": { L: 16, pattern: PATTERN.scorpionTail, eyes: EYES.araneid, depth: 0.7, carDepth: 0.55, gloss: 0.4, hair: 0.5, tissue: "#e8b774", accent: "#ecd29a", legTips: "#5c4122", legBandAt: "none" },
  "net-casting-spider": { L: 25, pattern: PATTERN.netCaster, eyes: EYES.deinopid, depth: 0.9, carDepth: 0.6, gloss: 0.3, hair: 0.75, tissue: "#a7835c", accent: "#b89a74", legTips: "#3b3025", legBandAt: "rings" },
  "magnificent-spider": { L: 14, pattern: PATTERN.magnificent, eyes: EYES.araneid, depth: 0.85, carDepth: 0.55, gloss: 0.5, hair: 0.3, tissue: "#f2d7b8", accent: "#f7ead6", legTips: "#9c7c68", legBandAt: "stripes" },
  "redback-spider": { L: 10, pattern: PATTERN.redback, eyes: EYES.theridiid, depth: 0.95, carDepth: 0.55, gloss: 1, hair: 0.1, tissue: "#7a2a26", translucency: 0.12, accent: "#e23c46", legTips: "#101014", legBandAt: "none" },
});

const FALLBACK = { L: 15, pattern: PATTERN.garden, eyes: EYES.araneid, depth: 0.8, carDepth: 0.55, gloss: 0.5, hair: 0.5, tissue: "#c49a5d", accent: "#d8c8a8", legTips: "#3a3028", legBandAt: "none" };

export function modelFor(id) {
  return MODELS[id] || FALLBACK;
}

function hex(value, fallback = "#808080") {
  const text = typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
  const n = parseInt(text.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255].map(v => Math.pow(v, 2.2));
}

// Everything about a species that does not change from frame to frame.
export function speciesUniforms(id, glyph) {
  const model = modelFor(id);
  const body = glyph.body || [];
  const abdomen = body[0] || { x: 0.32 * model.L, rx: 0.29 * model.L, ry: 0.19 * model.L, fill: "#806040" };
  const carapace = body[1] || { x: 0.76 * model.L, rx: 0.21 * model.L, ry: 0.14 * model.L, fill: "#806040" };
  const legs = glyph.legs || {};
  const widths = Array.isArray(legs.width) ? legs.width : [0.04 * model.L, 0.028 * model.L, 0.012 * model.L];
  const extras = body.slice(3);
  const extraFill = index => extras[index]?.fill;
  const abdRz = abdomen.ry * model.depth;
  const carRz = carapace.ry * model.carDepth;
  return {
    model,
    L: model.L,
    abd: [abdomen.x, abdomen.rx, abdomen.ry, abdRz],
    car: [carapace.x, carapace.rx, carapace.ry, carRz],
    bodyZ: [abdRz * 0.92, carRz * 1.05 + 0.02 * model.L],
    legR: widths.map(w => w * 0.5),
    colAbd: hex(abdomen.fill),
    colCar: hex(carapace.fill),
    colLeg: hex(legs.color, "#6a5a4a"),
    colBand: hex(legs.band || model.accent),
    hasBand: legs.band ? 1 : 0,
    colExtra1: hex(extraFill(0), model.accent),
    colExtra2: hex(extraFill(3) || extraFill(1), model.accent),
    colAccent: hex(model.accent),
    colTips: hex(model.legTips),
    colTissue: hex(model.tissue),
    pattern: model.pattern,
    eyes: model.eyes,
    translucency: model.translucency ?? 1,
    gloss: model.gloss,
    hair: model.hair,
    bandStyle: { none: 0, knee: 1, stripes: 2, rings: 3 }[model.legBandAt] ?? 0,
  };
}

// Lift a leg's four glyph joints (base, knee, ankle, tip) into seven 3-D points along coxa,
// femur, patella, tibia, metatarsus and tarsus. Knees rise off the web; swing legs lift their tips.
export function liftLeg(leg, species, lift) {
  const L = species.L;
  const [base, knee, ankle, tip] = leg;
  const z0 = species.bodyZ[1] * 0.75;
  const femur = Math.hypot(knee[0] - base[0], knee[1] - base[1]);
  const kneeZ = z0 + Math.max(0.12 * L, 0.42 * femur);
  const ankleZ = kneeZ * 0.52 + lift * 0.06 * L;
  const tipZ = 0.03 * L + lift * 0.14 * L;
  const mix = (a, b, t) => a + (b - a) * t;
  const coxa = [mix(base[0], knee[0], 0.1), mix(base[1], knee[1], 0.1), z0 + 0.04 * L];
  const patella = [mix(knee[0], ankle[0], 0.17), mix(knee[1], ankle[1], 0.17), kneeZ + 0.035 * L];
  const meta = [mix(ankle[0], tip[0], 0.62), mix(ankle[1], tip[1], 0.62), mix(ankleZ, tipZ, 0.7)];
  return [
    [base[0], base[1], z0], coxa, [knee[0], knee[1], kneeZ], patella,
    [ankle[0], ankle[1], ankleZ], meta, [tip[0], tip[1], tipZ],
  ];
}
