// Procedural eucalypt canopy behind the web, plus bokeh, motes and foreground leaves.
// Everything is generated once per seed/density/size/colour and animated in shaders,
// so wind never uploads buffers.
//
// Canopy space ("h-space"): x = (cssX - width/2) / height, y = cssY / height. It is anchored
// to the stage centre, so resizing reveals more or less canopy instead of regenerating it.

export const CANOPY_HALF_WIDTH = 2.6;
export const CANOPY_TOP = -0.55;
export const CANOPY_BOTTOM = 1.45;
export const INSTANCE_FLOATS = 16;

const KIND_LEAF = 0;
const KIND_BRANCH = 1;

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hexToRgb(hex) {
  const value = parseInt(String(hex).slice(1), 16);
  return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255];
}

function rgbToHsl([r, g, b]) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h / 6, s, l];
}

function hslToRgb([h, s, l]) {
  if (s === 0) return [l, l, l];
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = t => {
    t = ((t % 1) + 1) % 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [channel(h + 1 / 3), channel(h), channel(h - 1 / 3)];
}

class InstanceWriter {
  constructor() {
    this.items = [];
  }

  // a0: x, y, angle, length   a1: width, bend, depth, kind   a2: r, g, b, phase   a3: widthEnd, sway, lit, variant
  push(depth, values) {
    this.items.push({ depth, values });
  }

  pack() {
    // Far instances first so nearer leaves composite over them; ties keep generation order.
    const sorted = this.items.map((item, order) => ({ ...item, order }))
      .sort((a, b) => b.depth - a.depth || a.order - b.order);
    const data = new Float32Array(sorted.length * INSTANCE_FLOATS);
    sorted.forEach((item, i) => data.set(item.values, i * INSTANCE_FLOATS));
    return { data, count: sorted.length };
  }
}

function leafColor(base, random) {
  const [h, s, l] = rgbToHsl(base);
  const roll = random();
  if (roll < 0.03) return hslToRgb([0.03 + random() * 0.04, Math.min(1, s + 0.1), l * 0.9]); // red new growth
  if (roll < 0.07) return hslToRgb([0.12 + random() * 0.03, s * 0.8, Math.min(0.8, l * 1.2)]); // drying leaf
  return hslToRgb([h + (random() - 0.5) * 0.05, Math.max(0, Math.min(1, s * (0.8 + random() * 0.4))),
    Math.max(0.05, Math.min(0.85, l * (0.75 + random() * 0.5)))]);
}

function addLeaf(writer, random, x, y, angle, size, depth, color, sway, variant = 0) {
  const length = size * (0.8 + random() * 0.45);
  const width = length * (0.13 + random() * 0.09);
  const bend = (random() - 0.5) * 1.3;
  const lit = random() < 0.35 ? 0.75 + random() * 0.25 : Math.pow(random(), 2.2) * 0.6;
  writer.push(depth, [x, y, angle, length, width, bend, depth, KIND_LEAF,
    color[0], color[1], color[2], random() * Math.PI * 2, 0, sway * (0.7 + random() * 0.6), lit, variant]);
}

function growBranch(writer, random, options) {
  const { start, heading, length, width, depth, bark, leafBase, leafSize, leafEvery, twigs, sway, droop } = options;
  let [x, y] = start;
  let angle = heading;
  const step = 0.028;
  const steps = Math.max(3, Math.round(length / step));
  const path = [[x, y]];
  for (let i = 0; i < steps; i++) {
    const t = i / steps;
    // A small wander plus a steady droop towards hanging straight down under the foliage.
    const toDown = Math.atan2(Math.sin(Math.PI / 2 - angle), Math.cos(Math.PI / 2 - angle));
    angle += (random() - 0.5) * 0.22 + toDown * 0.025 * droop;
    const nx = x + Math.cos(angle) * step;
    const ny = y + Math.sin(angle) * step;
    const w0 = width * (1 - 0.8 * t);
    const w1 = width * (1 - 0.8 * (i + 1) / steps);
    writer.push(depth + 1e-4, [x, y, angle, step * 1.08, w0, 0, depth, KIND_BRANCH,
      bark[0], bark[1], bark[2], 0, w1, sway * t, 0.35, 0]);
    x = nx;
    y = ny;
    path.push([x, y]);
  }
  // Leaves from a third of the way out, alternating sides, pendulous like eucalypt foliage.
  let side = random() < 0.5 ? -1 : 1;
  const firstLeaf = Math.floor(path.length * 0.3);
  for (let i = firstLeaf; i < path.length - 1; i++) {
    if (random() > leafEvery) continue;
    const [px, py] = path[i];
    const [qx, qy] = path[i + 1];
    const dir = Math.atan2(qy - py, qx - px);
    side = -side;
    let leafAngle = dir + side * (0.45 + random() * 0.65);
    const hang = 0.35 + random() * 0.35;
    const down = Math.PI / 2;
    const delta = Math.atan2(Math.sin(down - leafAngle), Math.cos(down - leafAngle));
    leafAngle += delta * hang;
    const t = i / path.length;
    addLeaf(writer, random, px, py, leafAngle, leafSize * (0.75 + 0.45 * t), depth - 2e-4 * random(),
      leafColor(leafBase, random), sway * (0.6 + t));
  }
  // A drooping cluster at the tip.
  const [tx, ty] = path.at(-1);
  const cluster = 3 + Math.floor(random() * 3);
  for (let k = 0; k < cluster; k++) {
    const spread = (k / Math.max(1, cluster - 1) - 0.5) * 1.6;
    addLeaf(writer, random, tx, ty, angle + spread * 0.9 + (Math.PI / 2 - angle) * 0.35, leafSize * (0.8 + random() * 0.3),
      depth - 3e-4, leafColor(leafBase, random), sway * 1.4);
  }
  if (twigs > 0) {
    for (let k = 0; k < twigs; k++) {
      const at = Math.floor(path.length * (0.3 + random() * 0.55));
      const [bx, by] = path[at];
      const [cx, cy] = path[Math.min(path.length - 1, at + 1)];
      const dir = Math.atan2(cy - by, cx - bx);
      growBranch(writer, random, {
        ...options,
        start: [bx, by],
        heading: dir + (random() < 0.5 ? -1 : 1) * (0.5 + random() * 0.6),
        length: length * (0.25 + random() * 0.3),
        width: width * 0.45,
        twigs: 0,
        sway: sway * 1.2,
      });
    }
  }
}

// Branches reach in from the top and upper sides, so the upper stage is leafy and the web's
// middle stays open.
export function generateCanopy({ seed, density, leafSize, leafColor: colorHex }) {
  const random = mulberry32((seed * 2654435761) ^ 0x5bd1e995);
  const writer = new InstanceWriter();
  const leafBase = hexToRgb(colorHex);
  const bark = [0.2, 0.15, 0.11];
  const branches = density <= 0.001 ? 0 : Math.round(3 + density * 11);
  for (let b = 0; b < branches; b++) {
    const roll = random();
    let start;
    let heading;
    if (roll < 0.3) {
      // From above, leaning well away from vertical.
      start = [(random() * 2 - 1) * CANOPY_HALF_WIDTH * 0.7, CANOPY_TOP + 0.05];
      heading = Math.PI / 2 + (random() < 0.5 ? -1 : 1) * (0.6 + random() * 0.6);
    } else {
      // From the upper sides, reaching in across the stage.
      const sideSign = random() < 0.5 ? -1 : 1;
      start = [sideSign * (0.6 + random() * 1.1), CANOPY_TOP + 0.1 + Math.pow(random(), 1.5) * 1.1];
      heading = (sideSign < 0 ? 0 : Math.PI) + sideSign * (random() - 0.2) * 0.7;
    }
    const depth = 0.1 + random() * 0.9;
    growBranch(writer, random, {
      start, heading,
      length: 0.6 + random() * (0.6 + density * 0.5),
      width: 0.008 + random() * 0.012,
      depth,
      bark: bark.map(v => v * (0.8 + random() * 0.4)),
      leafBase,
      leafSize: 0.085 * leafSize,
      leafEvery: 0.55 + density * 0.4,
      twigs: 1 + Math.floor(random() * (2 + density * 3)),
      sway: 0.6 + random() * 0.6,
      droop: 0.25 + random() * 0.5,
    });
  }
  // Overhead canopy: a dense band of leaf clusters just above and beside the top of the stage.
  // The sun usually sits behind it, so its gaps are where light shafts come from.
  const overhead = density <= 0.001 ? 0 : Math.round(18 + density * 42);
  for (let k = 0; k < overhead; k++) {
    const side = random() < 0.25;
    const cx = side ? (random() < 0.5 ? -1 : 1) * (0.55 + random() * 1.4) : (random() * 2 - 1) * CANOPY_HALF_WIDTH * 0.85;
    const cy = side ? CANOPY_TOP + 0.1 + random() * 0.8 : CANOPY_TOP + 0.05 + random() * 0.5;
    const spread = 0.05 + random() * 0.09;
    const count = Math.round(16 + random() * 30 * (0.5 + density));
    const depth = 0.3 + random() * 0.5;
    const tint = leafColor(leafBase, random);
    const hang = Math.PI / 2 + (random() - 0.5) * 0.9;
    for (let n = 0; n < count; n++) {
      const gx = (random() + random() - 1) * spread * 1.6;
      const gy = (random() + random() - 1) * spread;
      const color = tint.map(v => v * (0.8 + random() * 0.4));
      addLeaf(writer, random, cx + gx, cy + gy, hang + (random() - 0.5) * 1.6, 0.075 * leafSize * (0.8 + random() * 0.5),
        depth + random() * 0.05, color, 0.8);
    }
  }
  // Far foliage: clusters of strongly defocused leaves that give the background its leafy texture.
  const clusters = density <= 0.001 ? 0 : Math.round(10 + density * 26);
  for (let k = 0; k < clusters; k++) {
    const cx = (random() * 2 - 1) * CANOPY_HALF_WIDTH * 0.75;
    const cy = CANOPY_TOP + 0.1 + Math.pow(random(), 0.8) * (CANOPY_BOTTOM - CANOPY_TOP - 0.2);
    const spread = 0.07 + random() * 0.12;
    const count = Math.round(18 + random() * 40 * (0.5 + density));
    const depth = 0.72 + random() * 0.28;
    const tint = leafColor(leafBase, random);
    for (let n = 0; n < count; n++) {
      const gx = (random() + random() + random() - 1.5) * spread * 1.4;
      const gy = (random() + random() + random() - 1.5) * spread;
      const angle = Math.PI / 2 + (random() - 0.5) * 2.2;
      const color = tint.map(v => v * (0.75 + random() * 0.5));
      addLeaf(writer, random, cx + gx, cy + gy, angle, 0.07 * leafSize * (0.8 + random() * 0.6), depth + random() * 0.02,
        color, 0.5);
    }
  }
  return writer.pack();
}

// Out-of-focus leaves close to the lens, in stage fractions so they hug the stage edges at any aspect.
export function generateForeground({ seed, amount, leafSize, leafColor: colorHex }) {
  const random = mulberry32((seed * 40503) ^ 0x9e3779b9);
  const writer = new InstanceWriter();
  const base = hexToRgb(colorHex);
  const spots = [
    [-0.04, 0.02, 0.5], [1.04, 0.05, 2.6], [0.02, 0.98, -0.5], [0.99, 1.0, 3.8], [0.35, -0.05, 1.7], [0.7, 1.05, -1.4],
  ];
  const count = Math.round(amount * spots.length);
  for (let i = 0; i < count; i++) {
    const [x, y, angle] = spots[i];
    const color = leafColor(base, random).map(v => v * 0.75);
    const length = (0.34 + random() * 0.18) * leafSize;
    writer.push(1 - i * 0.01, [x + (random() - 0.5) * 0.06, y + (random() - 0.5) * 0.05, angle + (random() - 0.5) * 0.5,
      length, length * (0.2 + random() * 0.06), (random() - 0.5) * 1.2, 1, KIND_LEAF,
      color[0], color[1], color[2], random() * Math.PI * 2, 0, 0.6 + random() * 0.4, 0.75, 1]);
  }
  return writer.pack();
}

// Bokeh: x, y in stage fractions; radius (h units); brightness; hue shift; phase; 2 spare.
export function generateBokeh({ seed }) {
  const random = mulberry32((seed * 69069) ^ 0x1b873593);
  const count = 110;
  const data = new Float32Array(count * 8);
  for (let i = 0; i < count; i++) {
    const y = Math.pow(random(), 1.6) * 1.1 - 0.05;
    data.set([random() * 1.1 - 0.05, y, 0.008 + Math.pow(random(), 2.2) * 0.05, Math.pow(random(), 3.2),
      (random() - 0.5), random() * Math.PI * 2, random(), 0], i * 8);
  }
  return { data, count };
}

// Motes: x, y in stage fractions; depth (-1 near lens .. 1 behind the web); size; phase; speed; 2 spare.
export function generateMotes({ seed }) {
  const random = mulberry32((seed * 1103515245) ^ 0x85ebca6b);
  const count = 420;
  const data = new Float32Array(count * 8);
  for (let i = 0; i < count; i++) {
    data.set([random(), random(), random() * 2 - 1, 0.4 + random() * 0.8, random() * Math.PI * 2, 0.5 + random(), random(), 0], i * 8);
  }
  return { data, count };
}
