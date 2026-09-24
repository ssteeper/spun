// Macro zoom for the Sunlit look: screen = stage × zoom + offset. The web plane (silk, dew,
// spiders) is magnified; the defocused backdrop stays put, which reads as depth.

export const MAX_ZOOM = 12;
const EASE_SECONDS = 0.28;

export class View {
  constructor() {
    this.zoom = 1;
    this.tx = 0;
    this.ty = 0;
    this.width = 1;
    this.height = 1;
    this.animation = null;
  }

  get identity() {
    return this.zoom === 1 && this.tx === 0 && this.ty === 0;
  }

  resize(width, height) {
    this.width = width;
    this.height = height;
    this.clamp();
  }

  // The magnified stage always covers the viewport.
  clamp() {
    this.zoom = Math.max(1, Math.min(MAX_ZOOM, this.zoom));
    this.tx = Math.min(0, Math.max(this.width * (1 - this.zoom), this.tx));
    this.ty = Math.min(0, Math.max(this.height * (1 - this.zoom), this.ty));
    if (Math.abs(this.zoom - 1) < 1e-4) {
      this.zoom = 1;
      this.tx = 0;
      this.ty = 0;
    }
  }

  toStage(x, y) {
    return { x: (x - this.tx) / this.zoom, y: (y - this.ty) / this.zoom };
  }

  // Zoom by `factor` keeping the screen point (x, y) fixed.
  zoomAt(x, y, factor) {
    this.animation = null;
    const target = Math.max(1, Math.min(MAX_ZOOM, this.zoom * factor));
    const applied = target / this.zoom;
    this.tx = x - (x - this.tx) * applied;
    this.ty = y - (y - this.ty) * applied;
    this.zoom = target;
    this.clamp();
  }

  panBy(dx, dy) {
    this.animation = null;
    this.tx += dx;
    this.ty += dy;
    this.clamp();
  }

  // Eased move to a zoom level centred on the screen point (x, y); returns the end state.
  animateTo(zoom, x, y, now = performance.now()) {
    const start = { zoom: this.zoom, tx: this.tx, ty: this.ty };
    const target = Math.max(1, Math.min(MAX_ZOOM, zoom));
    const stage = this.toStage(x, y);
    let tx = this.width / 2 - stage.x * target;
    let ty = this.height / 2 - stage.y * target;
    tx = Math.min(0, Math.max(this.width * (1 - target), tx));
    ty = Math.min(0, Math.max(this.height * (1 - target), ty));
    if (target === 1) {
      tx = 0;
      ty = 0;
    }
    this.animation = { start, end: { zoom: target, tx, ty }, t0: now };
    return this.animation.end;
  }

  reset(now) {
    return this.animateTo(1, this.width / 2, this.height / 2, now);
  }

  // Advances any eased move; true while it is still running.
  step(now = performance.now()) {
    if (!this.animation) return false;
    const { start, end, t0 } = this.animation;
    const u = Math.min(1, (now - t0) / (EASE_SECONDS * 1000));
    const e = 1 - Math.pow(1 - u, 3);
    // Interpolate zoom geometrically so the motion feels even.
    this.zoom = start.zoom * Math.pow(end.zoom / start.zoom, e);
    const blend = (a, b) => a + (b - a) * e;
    this.tx = blend(start.tx, end.tx);
    this.ty = blend(start.ty, end.ty);
    if (u >= 1) {
      this.zoom = end.zoom;
      this.tx = end.tx;
      this.ty = end.ty;
      this.animation = null;
    }
    this.clamp();
    return Boolean(this.animation);
  }

  finish() {
    if (this.animation) this.step(Infinity);
  }
}
