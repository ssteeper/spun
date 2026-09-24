import { Stage } from "./core/stage.js";
import { InstanceManager } from "./core/instances.js";
import { Renderer2D } from "./core/render2d.js";
import { SpiderOverlay } from "./core/overlay.js";
import { ViewerUI } from "./core/ui.js";
import { GLRenderer } from "./gl/glRenderer.js";

const query = new URLSearchParams(location.search);
const debugEnabled = query.get("debug") === "1";
const stageElement = document.querySelector("#stage");
const webCanvas = document.querySelector("#web-canvas");
const overlayCanvas = document.querySelector("#overlay-canvas");
const glCanvas = document.querySelector("#gl-canvas");
const BACKEND_KEY = "spun-backend";
const hint = document.querySelector("#stage-hint");
let manager;
let selectedId = null;
const ui = new ViewerUI({
  rows: document.querySelector("#species-rows"),
  status: document.querySelector("#status-pill"),
  liveStatus: document.querySelector("#live-status"),
  stageHint: hint,
  clearButton: document.querySelector("#clear-button"),
  modeGroup: document.querySelector("#mode-group"),
  backendGroup: document.querySelector("#backend-group"),
}, {
  onSelect(id) { selectedId = id; },
  onClear() { manager?.clear(); ui.clear(); },
  onBackend(value) { manager?.setBackend(value); },
});

const stage = new Stage(stageElement, webCanvas, overlayCanvas, glCanvas, () => manager?.resize());
const renderer2d = new Renderer2D(stage, null);
let glRenderer = null;
if (query.get("nogl") !== "1") {
  try {
    glRenderer = GLRenderer.create(glCanvas, stage, () => manager?.requestFrame());
  } catch (error) {
    console.warn("WebGL2 unavailable; using Canvas2D.", error);
    glRenderer = null;
  }
}
const renderers = glRenderer ? { "2d": renderer2d, gl: glRenderer } : { "2d": renderer2d };
function storedBackend() {
  try { return localStorage.getItem(BACKEND_KEY); } catch { return null; }
}
function showBackend(value) {
  glCanvas.classList.toggle("inactive", value !== "gl");
  if (value === "gl") {
    stage.ctx.save();
    stage.ctx.setTransform(1, 0, 0, 1, 0, 0);
    stage.ctx.clearRect(0, 0, webCanvas.width, webCanvas.height);
    stage.ctx.restore();
  }
  ui.setBackendState(Boolean(glRenderer), value);
}
const initialBackend = renderers[storedBackend()] ? storedBackend() : (glRenderer ? "gl" : "2d");
const overlay = new SpiderOverlay(stage);
manager = new InstanceManager({
  stage,
  renderers,
  backend: initialBackend,
  overlay,
  onBackend(value) {
    try { localStorage.setItem(BACKEND_KEY, value); } catch { /* storage unavailable */ }
    showBackend(value);
  },
  onStatus(instance, instanceCount) {
    if (!instance) {
      ui.resetStatus();
      return;
    }
    ui.setStatus(instance.specimen, instance.label, instance.cursor, instance.data, instanceCount);
  },
  onReady(manifest) {
    for (const renderer of Object.values(renderers)) renderer.stageConfig = manifest.stage;
    selectedId = manifest.defaultSpecimen;
    ui.renderSpecimens(manifest.specimens, selectedId);
  },
});
function plant(id, x, y) {
  ui.hideStageHint();
  return manager.plant(id, x, y);
}

stage.canvas.addEventListener("pointerdown", event => {
  if (event.button !== 0 && event.pointerType === "mouse") return;
  stage.canvas.focus({ preventScroll: true });
  const point = stage.localPoint(event.clientX, event.clientY);
  plant(selectedId, point.x, point.y);
});
stage.canvas.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    plant(selectedId, stage.width * 0.5, stage.height * 0.5);
  }
});

showBackend(manager.backend);
const ready = manager.initialize();
if (debugEnabled) {
  window.__spun = {
    ready,
    plant(id, x, y) { return plant(id, x, y); },
    seek(seconds) { manager.seek(seconds); },
    resume() { manager.resume(); },
    setBackend(value) { return manager.setBackend(value); },
    setMode(value) { return manager.setMode(value); },
    setGlow(value) { for (const renderer of Object.values(renderers)) renderer.setGlow(value); manager.requestFrame(); },
    glContext() { return glRenderer?.gl ?? null; },
    clear() { manager.clear(); },
    stats() { return manager.stats(); },
    decoded(id) { return manager.decodedCounts(id); },
  };
}

window.addEventListener("beforeunload", () => stage.destroy(), { once: true });
