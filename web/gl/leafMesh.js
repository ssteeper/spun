// Scaffold leaves are stored as outline records (spun/scaffold.py: leaf()): a closed margin at
// alpha 0.9, then an open midrib and paired veins. Rebuilding the closed margins as triangle fans
// lets the Sunlit look fill them as translucent leaves. Bark is always alpha 1, so it never matches.

const KIND_SCAFFOLD = 0;
const FLAG_ENV = 2;
const MARGIN_ALPHA = 230;
export const LEAF_VERTEX_FLOATS = 6; // x, y, s, t, birth record, leaf id

function isMarginCandidate(styles, i) {
  const o = i * 8;
  return styles[o] === KIND_SCAFFOLD && (styles[o + 6] & FLAG_ENV) !== 0 && styles[o + 7] === MARGIN_ALPHA;
}

function sameColor(styles, i, j) {
  const a = i * 8;
  const b = j * 8;
  return styles[a + 2] === styles[b + 2] && styles[a + 3] === styles[b + 3] && styles[a + 4] === styles[b + 4];
}

export function buildLeafMesh(data) {
  const { coords, styles, count } = data;
  const vertices = [];
  let leafId = 0;
  let i = 0;
  while (i < count) {
    if (!isMarginCandidate(styles, i)) {
      i++;
      continue;
    }
    let j = i;
    while (j + 1 < count && isMarginCandidate(styles, j + 1) && sameColor(styles, i, j + 1) &&
      Math.abs(coords[j * 4 + 2] - coords[(j + 1) * 4]) < 0.01 && Math.abs(coords[j * 4 + 3] - coords[(j + 1) * 4 + 1]) < 0.01) j++;
    const closed = Math.hypot(coords[j * 4 + 2] - coords[i * 4], coords[j * 4 + 3] - coords[i * 4 + 1]) < 0.6;
    if (closed && j - i >= 5) {
      const points = [];
      for (let k = i; k <= j; k++) points.push([coords[k * 4], coords[k * 4 + 1]]);
      appendLeaf(vertices, points, j, leafId++);
    }
    i = j + 1;
  }
  return { data: new Float32Array(vertices), count: vertices.length / LEAF_VERTEX_FLOATS, leaves: leafId };
}

function appendLeaf(out, points, birth, id) {
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
  const centre = [cx, cy];
  const [cs] = local(centre);
  for (let k = 0; k < points.length; k++) {
    const a = points[k];
    const b = points[(k + 1) % points.length];
    const [as, at] = local(a);
    const [bs, bt] = local(b);
    out.push(cx, cy, cs, 0, birth, id, a[0], a[1], as, at, birth, id, b[0], b[1], bs, bt, birth, id);
  }
}
