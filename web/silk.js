const HEADER_BYTES = 32;
const RECORD_BYTES = 20;
const BEAD_BYTES = 8;
const NEVER = 0xffffffff;
const ENV = 1 << 1;
const INVISIBLE = 1 << 2;

export function parseSilk(rawBuffer, specimen = null) {
  if (!(rawBuffer instanceof ArrayBuffer)) throw new TypeError(".silk data must be an ArrayBuffer");
  if (rawBuffer.byteLength < HEADER_BYTES) throw new RangeError("Truncated .silk header");
  const view = new DataView(rawBuffer);
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== "SILK") throw new TypeError("Invalid .silk magic");
  const version = view.getUint16(4, true);
  const headerSize = view.getUint16(6, true);
  const recordSize = view.getUint16(8, true);
  const beadSize = view.getUint16(10, true);
  const count = view.getUint32(12, true);
  const beadCount = view.getUint32(16, true);
  const width = view.getUint16(20, true);
  const height = view.getUint16(22, true);
  const coordScale = view.getUint16(24, true);
  const widthScale = view.getUint8(26);
  const builderCount = view.getUint8(28);
  if (version !== 1 || headerSize !== HEADER_BYTES || recordSize !== RECORD_BYTES || beadSize !== BEAD_BYTES) {
    throw new TypeError("Unsupported .silk format version or record layout");
  }
  if (coordScale !== 4 || widthScale !== 32 || builderCount < 1 || builderCount > 3) {
    throw new TypeError("Invalid .silk scale or builder count");
  }
  const expectedBytes = HEADER_BYTES + count * RECORD_BYTES + beadCount * BEAD_BYTES;
  if (!Number.isSafeInteger(expectedBytes) || expectedBytes !== rawBuffer.byteLength) throw new RangeError("Invalid .silk payload size");
  if (specimen && (count !== specimen.segments || beadCount !== specimen.beads || width !== specimen.width || height !== specimen.height)) {
    throw new RangeError(`.silk counts or dimensions disagree with index for ${specimen.id}`);
  }

  const coords = new Float32Array(count * 4);
  const deaths = new Uint32Array(count);
  const styles = new Uint8Array(count * 8);
  const lengths = new Float32Array(count);
  const colors = new Array(count);
  const colorCache = new Map();
  const widths = new Float32Array(count);
  const alphas = new Float32Array(count);
  const cumulativeLength = new Float32Array(count);
  const temporary = [];
  const builderLengths = new Float64Array(builderCount);
  const recordOffset = HEADER_BYTES;
  for (let i = 0; i < count; i++) {
    const offset = recordOffset + i * RECORD_BYTES;
    const p = i * 4;
    const x0 = view.getUint16(offset, true) / coordScale;
    const y0 = view.getUint16(offset + 2, true) / coordScale;
    const x1 = view.getUint16(offset + 4, true) / coordScale;
    const y1 = view.getUint16(offset + 6, true) / coordScale;
    coords[p] = x0; coords[p + 1] = y0; coords[p + 2] = x1; coords[p + 3] = y1;
    const death = view.getUint32(offset + 8, true);
    deaths[i] = death;
    const styleOffset = i * 8;
    for (let j = 0; j < 8; j++) styles[styleOffset + j] = view.getUint8(offset + 12 + j);
    const rgbKey = (styles[styleOffset + 2] << 16) | (styles[styleOffset + 3] << 8) | styles[styleOffset + 4];
    let color = colorCache.get(rgbKey);
    if (color === undefined) {
      color = `rgb(${styles[styleOffset + 2]} ${styles[styleOffset + 3]} ${styles[styleOffset + 4]})`;
      colorCache.set(rgbKey, color);
    }
    colors[i] = color;
    widths[i] = styles[styleOffset + 1] / widthScale;
    alphas[i] = styles[styleOffset + 7] / 255;
    const length = Math.hypot(x1 - x0, y1 - y0);
    lengths[i] = length;
    const flags = styles[styleOffset + 6];
    const builder = (flags >> 4) & 3;
    if (builder >= builderCount) throw new RangeError(`Record ${i} refers to a missing builder`);
    if ((flags & ENV) === 0) builderLengths[builder] += length;
    cumulativeLength[i] = builderLengths[builder];
    if (death !== NEVER) temporary.push(i);
  }

  const beadsOffset = recordOffset + count * RECORD_BYTES;
  const beadHosts = new Uint32Array(beadCount);
  const beadT = new Float32Array(beadCount);
  const beadRadii = new Float32Array(beadCount);
  const beadFlags = new Uint8Array(beadCount);
  const beadX = new Float32Array(beadCount);
  const beadY = new Float32Array(beadCount);
  const beadStart = new Uint32Array(count);
  const beadEnd = new Uint32Array(count);
  let previousHost = -1;
  let previousPosition = -1;
  for (let i = 0; i < beadCount; i++) {
    const offset = beadsOffset + i * BEAD_BYTES;
    const host = view.getUint32(offset, true);
    if (host >= count) throw new RangeError(`Bead ${i} refers to missing host ${host}`);
    const tValue = view.getUint16(offset + 4, true);
    if (host < previousHost || (host === previousHost && tValue < previousPosition)) throw new RangeError("Beads must be sorted by host and position");
    const t = tValue / 65535;
    const radius = view.getUint8(offset + 6) / 16;
    const flags = view.getUint8(offset + 7);
    const p = host * 4;
    beadHosts[i] = host;
    beadT[i] = t;
    beadRadii[i] = radius;
    beadFlags[i] = flags;
    beadX[i] = coords[p] + (coords[p + 2] - coords[p]) * t;
    beadY[i] = coords[p + 1] + (coords[p + 3] - coords[p + 1]) * t;
    if (host !== previousHost) beadStart[host] = i;
    beadEnd[host] = i + 1;
    previousHost = host;
    previousPosition = tValue;
  }

  return {
    rawBuffer, count, beadCount, width, height, coordScale, widthScale, builderCount,
    coords, deaths, styles, lengths, cumulativeLength, builderLengths, colors, widths, alphas,
    temporary: Uint32Array.from(temporary), beadHosts, beadT, beadRadii, beadFlags, beadX, beadY, beadStart, beadEnd,
    specimen,
    cursorAt(seconds) { return cursorAt(specimen, seconds, count); },
    labelAt(cursor) { return labelAt(specimen, cursor, count); },
    minLod,
    hash32,
  };
}

export function cursorAt(specimen, seconds, count = specimen?.segments ?? 0) {
  if (!specimen || !Array.isArray(specimen.timeline) || specimen.timeline.length !== 512) throw new TypeError("Specimen requires a 512-sample timeline");
  const duration = Math.max(0, Number(specimen.durationSeconds) || 0);
  const t = Math.max(0, Math.min(duration, Number(seconds) || 0));
  if (duration === 0 || t >= duration) return count;
  const sample = t / duration * 511;
  const low = Math.floor(sample);
  const fraction = sample - low;
  const a = specimen.timeline[low];
  const b = specimen.timeline[Math.min(511, low + 1)];
  return Math.max(0, Math.min(count, a + (b - a) * fraction));
}

export function labelAt(specimen, cursor, count = specimen?.segments ?? 0) {
  if (!specimen || !Array.isArray(specimen.stages) || specimen.stages.length === 0) return "building";
  if (cursor >= count) return "at rest";
  let label = specimen.stages[0].label;
  for (let i = 1; i < specimen.stages.length; i++) {
    if (specimen.stages[i].start > cursor) break;
    label = specimen.stages[i].label;
  }
  return label;
}

export function minLod(detail) {
  const d = Math.max(1e-3, Math.min(1, Number(detail) || 1e-3));
  return d >= 0.9 ? 0 : Math.round(255 * (1 - d / 0.9));
}

export function hash32(value) {
  let x = Number(value) >>> 0;
  x ^= x >>> 16;
  x = Math.imul(x, 0x85ebca6b);
  x ^= x >>> 13;
  x = Math.imul(x, 0xc2b2ae35);
  x ^= x >>> 16;
  return x >>> 0;
}
