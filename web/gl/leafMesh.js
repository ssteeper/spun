// Closed outlines the Sunlit look fills as solid shapes:
// - scaffold leaves (spun/scaffold.py: leaf()): a closed SCAFFOLD margin at alpha 0.9, then an open
//   midrib and veins; bark is always alpha 1, so it never matches;
// - the leaf-curler's hauled leaf (species/phonognatha.py): a closed LEAF outline at alpha 0.95;
// - egg sacs (species/arachnura.py ovals, spun/snares.py spindles): closed EGGSAC outlines.
// Each closed chain of same-coloured, end-to-end records becomes a triangle fan.

const KIND_SCAFFOLD = 0;
const KIND_LEAF = 1;
const KIND_EGGSAC = 10;
const FLAG_ENV = 2;
const FLAG_INVISIBLE = 4;
export const MATERIAL = Object.freeze({ leaf: 0, dryLeaf: 1, eggSac: 2 });
// x, y, s (base to tip), t (across, -1..1), birth record, shape id, material, r, g, b (sRGB)
export const LEAF_VERTEX_FLOATS = 10;

function materialOf(styles, i) {
  const o = i * 8;
  const kind = styles[o];
  const flags = styles[o + 6];
  const alpha = styles[o + 7];
  if (flags & FLAG_INVISIBLE) return -1;
  if (kind === KIND_EGGSAC) return MATERIAL.eggSac;
  if (!(flags & FLAG_ENV)) return -1;
  if (kind === KIND_SCAFFOLD && alpha === 230) return MATERIAL.leaf;
  if (kind === KIND_LEAF && alpha === 242) return MATERIAL.dryLeaf;
  return -1;
}

function sameColor(styles, i, j) {
  const a = i * 8;
  const b = j * 8;
  return styles[a + 2] === styles[b + 2] && styles[a + 3] === styles[b + 3] && styles[a + 4] === styles[b + 4];
}

function joined(coords, i, j) {
  return Math.abs(coords[i * 4 + 2] - coords[j * 4]) < 0.01 && Math.abs(coords[i * 4 + 3] - coords[j * 4 + 1]) < 0.01;
}

export function buildLeafMesh(data) {
  const { coords, styles, count } = data;
  const vertices = [];
  let shapes = 0;
  let i = 0;
  while (i < count) {
    const material = materialOf(styles, i);
    if (material < 0) {
      i++;
      continue;
    }
    // Follow the chain; it closes as soon as a record ends where the chain began.
    let j = i;
    let closed = false;
    for (;;) {
      if (Math.hypot(coords[j * 4 + 2] - coords[i * 4], coords[j * 4 + 3] - coords[i * 4 + 1]) < 0.6 && j - i >= 5) {
        closed = true;
        break;
      }
      const next = j + 1;
      if (next >= count || materialOf(styles, next) !== material || !sameColor(styles, i, next) || !joined(coords, j, next)) break;
      j = next;
    }
    if (closed) {
      const points = [];
      for (let k = i; k <= j; k++) points.push([coords[k * 4], coords[k * 4 + 1]]);
      const rgb = [styles[i * 8 + 2] / 255, styles[i * 8 + 3] / 255, styles[i * 8 + 4] / 255];
      appendShape(vertices, points, j, shapes++, material, rgb);
    }
    i = j + 1;
  }
  return { data: new Float32Array(vertices), count: vertices.length / LEAF_VERTEX_FLOATS, shapes };
}

function appendShape(out, points, birth, id, material, rgb) {
  const base = points[0];
  let tip = base;
  let far = 0;
  for (const point of points) {
    const d = Math.hypot(point[0] - base[0], point[1] - base[1]);
    if (d > far) {
      far = d;
      tip = point;
    }
  }
  if (far < 1e-3) return;
  const ax = (tip[0] - base[0]) / far;
  const ay = (tip[1] - base[1]) / far;
  let halfWidth = 1e-3;
  for (const [x, y] of points) halfWidth = Math.max(halfWidth, Math.abs(-(x - base[0]) * ay + (y - base[1]) * ax));
  const local = ([x, y]) => [
    ((x - base[0]) * ax + (y - base[1]) * ay) / far,
    (-(x - base[0]) * ay + (y - base[1]) * ax) / halfWidth,
  ];
  let cx = 0;
  let cy = 0;
  for (const [x, y] of points) {
    cx += x;
    cy += y;
  }
  cx /= points.length;
  cy /= points.length;
  const [cs, ct] = local([cx, cy]);
  const tail = [birth, id, material, ...rgb];
  for (let k = 0; k < points.length; k++) {
    const a = points[k];
    const b = points[(k + 1) % points.length];
    const [as, at] = local(a);
    const [bs, bt] = local(b);
    out.push(cx, cy, cs, ct, ...tail, a[0], a[1], as, at, ...tail, b[0], b[1], bs, bt, ...tail);
  }
}
