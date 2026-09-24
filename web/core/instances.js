import { parseSilk } from "../silk.js";

const INSTANCE_LIMIT = 12;
const INSET = 4;
const REST_SECONDS = 0.5;
const DEW_SECONDS = 2.4 + 0.35; // latest start 2.4 s·u_i plus 0.35 s growth
const ENV = 1 << 1;

function timeAtCursor(specimen, target) {
  const timeline = specimen.timeline;
  let low = 0;
  let high = timeline.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (timeline[mid] >= target) high = mid;
    else low = mid + 1;
  }
  if (low === 0) return 0;
  const previous = timeline[low - 1];
  const span = timeline[low] - previous;
  const fraction = span > 0 ? (target - previous) / span : 0;
  return ((low - 1 + Math.max(0, Math.min(1, fraction))) / 511) * specimen.durationSeconds;
}

function builderRange(data) {
  const first = new Array(data.builderCount).fill(null);
  const last = new Array(data.builderCount).fill(null);
  for (let i = 0; i < data.count; i++) {
    const flags = data.styles[i * 8 + 6];
    if (flags & ENV) continue;
    const builder = (flags >> 4) & 3;
    if (first[builder] == null) first[builder] = i;
    last[builder] = i;
  }
  const startSeconds = new Array(data.builderCount).fill(0);
  const finishSeconds = new Array(data.builderCount).fill(0);
  for (let builder = 0; builder < data.builderCount; builder++) {
    if (first[builder] == null) continue;
    startSeconds[builder] = timeAtCursor(data.specimen, first[builder]);
    finishSeconds[builder] = timeAtCursor(data.specimen, last[builder] + 1);
  }
  return { first, last, startSeconds, finishSeconds };
}

export class InstanceManager {
  constructor({ stage, renderers, backend = "2d", overlay, onStatus = () => {}, onReady = () => {}, onBackend = () => {} }) {
    this.stage = stage;
    this.renderers = renderers;
    this.onBackend = onBackend;
    this.backend = renderers[backend] ? backend : "2d";
    this.renderer = renderers[this.backend];
    this.overlay = overlay;
    this.onStatus = onStatus;
    this.onReady = onReady;
    this.manifest = null;
    this.assets = new Map();
    this.instances = [];
    this.nextId = 1;
    this.rafActive = false;
    this.rafId = 0;
    this.framesRendered = 0;
    this.lastTimestamp = null;
    this.frozen = false;
    this.mode = "dusk";
    this.reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", event => {
      this.reducedMotion = event.matches;
    });
    this.lastStatusAt = -Infinity;
    this.lastStatusLabel = null;
  }

  async initialize() {
    const response = await fetch("./specimens/index.json");
    if (!response.ok) throw new Error(`Could not load specimen index (${response.status})`);
    this.manifest = await response.json();
    if (this.manifest.version !== 1 || !Array.isArray(this.manifest.specimens) || !this.manifest.specimens.length) {
      throw new TypeError("Invalid specimen index");
    }
    this.onReady(this.manifest);
    const defaultSpecimen = this.manifest.specimens.find(item => item.id === this.manifest.defaultSpecimen);
    if (!defaultSpecimen) throw new TypeError("Default specimen is missing from the index");
    await this.load(defaultSpecimen);
    return this.manifest;
  }

  async load(specimen) {
    if (this.assets.has(specimen.id)) return this.assets.get(specimen.id);
    const task = (async () => {
      const response = await fetch(`./specimens/${encodeURIComponent(specimen.file)}`);
      if (!response.ok) throw new Error(`Could not load ${specimen.file} (${response.status})`);
      const data = parseSilk(await response.arrayBuffer(), specimen);
      data.builderInfo = builderRange(data);
      this.assets.set(specimen.id, data);
      return data;
    })();
    this.assets.set(specimen.id, task);
    try {
      return await task;
    } catch (error) {
      this.assets.delete(specimen.id);
      throw error;
    }
  }

  async plant(id, x = this.stage.width * 0.5, y = this.stage.height * 0.5) {
    if (!this.manifest) await this.initialize();
    const specimen = this.manifest.specimens.find(item => item.id === id);
    if (!specimen) throw new RangeError(`Unknown specimen: ${id}`);
    const data = await this.load(specimen);
    const builderInfo = data.builderInfo;
    const instance = {
      instanceId: this.nextId++,
      specimen,
      data,
      elapsed: 0,
      duration: Math.max(0, Number(specimen.durationSeconds) || 0),
      cursor: 0,
      label: data.labelAt(0),
      dewOrigin: null,
      dewAge: -1,
      reducedMotion: this.reducedMotion,
      builderFirst: builderInfo.first,
      builderLast: builderInfo.last,
      builderStartSeconds: builderInfo.startSeconds,
      builderFinishSeconds: builderInfo.finishSeconds,
      buffers: null,
      placement: null,
      normalizedX: this.stage.width ? x / this.stage.width : 0.5,
      normalizedY: this.stage.height ? y / this.stage.height : 0.5,
    };
    if (this.mode === "dawn") instance.dewOrigin = instance.duration;
    if (instance.reducedMotion) instance.elapsed = this.endTime(instance);
    this.place(instance);
    if (this.instances.length === INSTANCE_LIMIT) {
      const removed = this.instances.shift();
      this.renderers["2d"].invalidate(removed);
    }
    this.instances.push(instance);
    this.frozen = false;
    this.lastTimestamp = null;
    this.onStatus(instance, this.instances.length);
    this.requestFrame();
    return instance;
  }

  place(instance) {
    const specimen = instance.specimen;
    const bounds = specimen.bounds || { minX: 0, minY: 0, maxX: specimen.width, maxY: specimen.height };
    const anchor = specimen.anchor || { x: specimen.width * 0.5, y: specimen.height * 0.5 };
    const width = this.stage.width;
    const height = this.stage.height;
    const ideal = Math.max(1e-6, Math.min(0.6 * height / Math.max(1, bounds.maxY - bounds.minY), 0.6 * width / Math.max(1, bounds.maxX - bounds.minX)));
    const floor = ideal * 0.12;
    const requestedX = instance.normalizedX * width;
    const requestedY = instance.normalizedY * height;
    const maxScale = (available, extent) => extent > 0 ? available / extent : Infinity;
    const scale = Math.max(floor, Math.min(
      ideal,
      maxScale(requestedX - INSET, anchor.x - bounds.minX),
      maxScale(width - INSET - requestedX, bounds.maxX - anchor.x),
      maxScale(requestedY - INSET, anchor.y - bounds.minY),
      maxScale(height - INSET - requestedY, bounds.maxY - anchor.y),
    ));
    const minRelX = (bounds.minX - anchor.x) * scale;
    const maxRelX = (bounds.maxX - anchor.x) * scale;
    const minRelY = (bounds.minY - anchor.y) * scale;
    const maxRelY = (bounds.maxY - anchor.y) * scale;
    let x = requestedX;
    let y = requestedY;
    const doesNotFit = x + minRelX < INSET || x + maxRelX > width - INSET ||
      y + minRelY < INSET || y + maxRelY > height - INSET;
    if (scale === floor && doesNotFit) {
      x = Math.min(width - INSET - maxRelX, Math.max(INSET - minRelX, requestedX));
      y = Math.min(height - INSET - maxRelY, Math.max(INSET - minRelY, requestedY));
    }
    const originX = x - anchor.x * scale;
    const originY = y - anchor.y * scale;
    const left = originX + bounds.minX * scale;
    const top = originY + bounds.minY * scale;
    const right = originX + bounds.maxX * scale;
    const bottom = originY + bounds.maxY * scale;
    instance.placement = {
      x, y, anchorX: x, anchorY: y, originX, originY, scale,
      idealScale: ideal,
      detail: Math.max(1e-3, Math.min(1, scale / ideal)),
      screenBounds: { left, top, width: Math.max(1, right - left), height: Math.max(1, bottom - top) },
    };
    if (instance.buffers) this.renderers["2d"].invalidate(instance);
  }

  endTime(instance) {
    const settled = instance.duration + REST_SECONDS;
    return instance.dewOrigin == null ? settled : Math.max(settled, instance.dewOrigin + DEW_SECONDS);
  }

  advance() {
    for (const instance of this.instances) {
      instance.cursor = instance.data.cursorAt(Math.min(instance.duration, instance.elapsed));
      instance.label = instance.data.labelAt(instance.cursor);
      const complete = instance.cursor >= instance.data.count;
      instance.dewAge = complete && instance.dewOrigin != null ? Math.max(-1, instance.elapsed - instance.dewOrigin) : -1;
    }
  }

  dewVisible(instance) {
    if (instance.dewAge < 0 || instance.placement.detail < 0.35) return 0;
    const { data } = instance;
    const threshold = data.minLod(instance.placement.detail);
    let count = 0;
    for (let b = 0; b < data.beadCount; b++) {
      if (data.beadFlags[b] & 2) continue;
      if (data.styles[data.beadHosts[b] * 8 + 5] < threshold) continue;
      if (instance.dewAge > 2.4 * data.beadU[b]) count++;
    }
    return count;
  }

  resize() {
    for (const instance of this.instances) this.place(instance);
    this.requestFrame();
  }

  requestFrame() {
    if (this.rafActive) return;
    this.rafActive = true;
    this.rafId = requestAnimationFrame(timestamp => this.frame(timestamp));
  }

  frame(timestamp) {
    this.rafId = 0;
    if (this.lastTimestamp == null) this.lastTimestamp = timestamp;
    const delta = this.frozen ? 0 : Math.max(0, (timestamp - this.lastTimestamp) / 1000);
    this.lastTimestamp = timestamp;
    if (delta > 0) {
      for (const instance of this.instances) {
        instance.elapsed = Math.min(this.endTime(instance), instance.elapsed + delta);
      }
    }
    this.advance();
    this.renderer.render(this.instances);
    this.overlay.draw(this.instances);
    this.framesRendered++;
    this.updateStatus(timestamp);
    if (!this.frozen && this.instances.some(instance => instance.elapsed < this.endTime(instance))) {
      this.rafId = requestAnimationFrame(next => this.frame(next));
      return;
    }
    this.rafActive = false;
    this.lastTimestamp = null;
  }

  updateStatus(timestamp = performance.now()) {
    const instance = this.instances.at(-1);
    if (!instance) {
      this.onStatus(null);
      return;
    }
    if (timestamp - this.lastStatusAt >= 250 || instance.label !== this.lastStatusLabel || instance.cursor >= instance.data.count) {
      this.onStatus(instance, this.instances.length);
      this.lastStatusAt = timestamp;
      this.lastStatusLabel = instance.label;
    }
  }

  seek(seconds) {
    if (seconds === "end") {
      for (const instance of this.instances) instance.elapsed = this.endTime(instance);
    } else {
      const value = Math.max(0, Number(seconds) || 0);
      for (const instance of this.instances) instance.elapsed = Math.min(this.endTime(instance), value);
    }
    this.frozen = true;
    this.lastTimestamp = null;
    this.advance();
    this.updateStatus();
    this.requestFrame();
  }

  resume() {
    if (!this.instances.length) return;
    this.frozen = false;
    this.lastTimestamp = null;
    this.requestFrame();
  }

  clear() {
    this.instances.length = 0;
    this.renderer.render([]);
    this.overlay.draw([]);
    this.frozen = false;
    this.rafActive = false;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = 0;
    this.lastTimestamp = null;
    this.updateStatus();
  }

  setBackend(value) {
    if (!this.renderers[value]) return false;
    if (value === this.backend) return true;
    this.backend = value;
    this.renderer = this.renderers[value];
    this.onBackend(value);
    this.requestFrame();
    return true;
  }

  setMode(value) {
    if (value !== "dusk" && value !== "dawn") return false;
    if (value === this.mode) return true;
    this.mode = value;
    for (const renderer of Object.values(this.renderers)) renderer.mode = value;
    for (const instance of this.instances) {
      if (value === "dawn") {
        // Dew clock origin: the later of the web's completion and the moment Dawn was switched on.
        instance.dewOrigin = Math.max(instance.duration, instance.elapsed);
        if (instance.reducedMotion) instance.elapsed = this.endTime(instance);
      } else {
        instance.dewOrigin = null;
        instance.elapsed = Math.min(instance.elapsed, this.endTime(instance));
      }
    }
    this.advance();
    this.requestFrame();
    return true;
  }

  decodedCounts(id) {
    const data = this.assets.get(id);
    if (!data || data instanceof Promise) return null;
    return { segments: data.count, beads: data.beadCount };
  }

  stats() {
    return {
      backend: this.backend,
      instances: this.instances.length,
      rafActive: this.rafActive,
      framesRendered: this.framesRendered,
      glBufferUploadsLastFrame: this.backend === "gl" ? this.renderers.gl.glBufferUploadsLastFrame : 0,
      glBufferUploadsTotal: this.renderers.gl?.glBufferUploadsTotal ?? 0,
      recordsDrawnLastFrame: this.renderer.recordsDrawnLastFrame,
      temporaryRecordsDrawnLastFrame: this.renderer.temporaryRecordsDrawnLastFrame,
      beadsDrawnLastFrame: this.renderer.beadsDrawnLastFrame,
      glRenderer: this.renderers.gl?.rendererName ?? null,
      mode: this.mode,
      dewVisible: this.instances.reduce((sum, instance) => sum + this.dewVisible(instance), 0),
      dewAges: this.instances.map(instance => instance.dewAge),
      decodedCounts: Object.fromEntries([...this.assets].filter(([, data]) => !(data instanceof Promise)).map(([id, data]) => [id, { segments: data.count, beads: data.beadCount }])),
      cursors: this.instances.map(instance => ({ id: instance.specimen.id, cursor: instance.cursor, elapsed: instance.elapsed, label: instance.label })),
      placements: this.instances.map(instance => ({
        id: instance.specimen.id,
        anchorX: instance.placement.anchorX,
        anchorY: instance.placement.anchorY,
        scale: instance.placement.scale,
        idealScale: instance.placement.idealScale,
        detail: instance.placement.detail,
        minLod: instance.data.minLod(instance.placement.detail),
        glowPad: instance.buffers?.glowPad ?? null,
        bounds: { ...instance.placement.screenBounds },
      })),
    };
  }
}
