export class Stage {
  constructor(stageElement, webCanvas, overlayCanvas, glCanvas, onResize = () => {}) {
    this.element = stageElement;
    this.canvas = webCanvas;
    this.overlayCanvas = overlayCanvas;
    this.glCanvas = glCanvas;
    this.ctx = webCanvas.getContext("2d", { alpha: true });
    this.overlayCtx = overlayCanvas.getContext("2d", { alpha: true });
    if (!this.ctx || !this.overlayCtx) throw new Error("Canvas2D is unavailable");
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this.onResize = onResize;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(stageElement);
    window.addEventListener("resize", () => this.resize(), { passive: true });
    this.resize();
  }

  resize() {
    const bounds = this.element.getBoundingClientRect();
    const width = Math.max(1, bounds.width);
    const height = Math.max(1, bounds.height);
    const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    const changed = width !== this.width || height !== this.height || dpr !== this.dpr;
    if (!changed) return;
    this.width = width;
    this.height = height;
    this.dpr = dpr;
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    for (const canvas of [this.canvas, this.overlayCanvas, this.glCanvas]) {
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    }
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.overlayCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.onResize({ width, height, dpr });
  }

  localPoint(clientX, clientY) {
    const rect = this.element.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top };
  }

  destroy() {
    this.resizeObserver.disconnect();
  }
}
