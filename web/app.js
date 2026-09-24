import { Stage } from "./core/stage.js";
import { InstanceManager } from "./core/instances.js";
import { Renderer2D } from "./core/render2d.js";
import { SpiderOverlay } from "./core/overlay.js";
import { ViewerUI } from "./core/ui.js";
import { SceneSettings } from "./core/settings.js";
import { ScenePanel } from "./core/panel.js";
import { GLRenderer } from "./gl/glRenderer.js";

const query = new URLSearchParams(location.search);
const debugEnabled = query.get("debug") === "1";
const stageElement = document.querySelector("#stage");
const webCanvas = document.querySelector("#web-canvas");
const overlayCanvas = document.querySelector("#overlay-canvas");
const glCanvas = document.querySelector("#gl-canvas");
const BACKEND_KEY = "spun-backend";
const hint = document.querySelector("#stage-hint");
const settings = new SceneSettings();
const shared = /(?:^#|&)scene=([A-Za-z0-9_-]+)/.exec(location.hash);
if (shared && settings.applyShareString(shared[1])) history.replaceState(null, "", location.pathname + location.search);
if (query.get("look") === "classic" || query.get("look") === "sunlit") settings.set("look", query.get("look"));

let manager;
let selectedId = null;
let panel = null;
const ui = new ViewerUI({
  rows: document.querySelector("#species-rows"),
  status: document.querySelector("#status-pill"),
  liveStatus: document.querySelector("#live-status"),
  stageHint: hint,
  clearButton: document.querySelector("#clear-button"),
  modeGroup: document.querySelector("#mode-group"),
}, {
  onSelect(id) { selectedId = id; },
  onClear() { manager?.clear(); ui.clear(); },
  onEscape() {
    // Escape closes the Scene panel first; with it closed, Escape clears the stage.
    if (panel?.isOpen()) {
      panel.setOpen(false);
      document.querySelector("#scene-button").focus();
      return;
    }
    manager?.clear();
    ui.clear();
  },
  onMode(value) {
    manager?.setMode(value);
    panel?.refresh();
  },
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
  panel?.setBackendState(Boolean(glRenderer), value);
  document.body.dataset.look = manager?.effectiveLook() ?? "classic";
  if (manager) updateZoomHud();
}
const initialBackend = renderers[storedBackend()] ? storedBackend() : (glRenderer ? "gl" : "2d");
const overlay = new SpiderOverlay(stage);
manager = new InstanceManager({
  stage,
  renderers,
  backend: initialBackend,
  overlay,
  settings,
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
  onFrame() {
    updateZoomHud();
  },
});

panel = new ScenePanel({
  panel: document.querySelector("#scene-panel"),
  toggle: document.querySelector("#scene-button"),
  settings,
  getMode: () => manager.mode,
  backend: {
    available: () => Boolean(glRenderer?.sunlitAvailable),
    current: () => manager.backend,
    set: value => manager.setBackend(value),
  },
});

settings.subscribe((values, change) => {
  if (change.reset || change.path.startsWith("dew")) manager.refreshDew();
  document.body.dataset.look = manager.effectiveLook();
  if (manager.effectiveLook() === "classic" && manager.backend === "gl") showBackend("gl");
  manager.requestFrame();
});

function plant(id, x, y) {
  ui.hideStageHint();
  return manager.plant(id, x, y);
}

// Stage input. Classic: a press plants at once. Sunlit: the wheel, a pinch or the zoom buttons
// magnify the web; while zoomed, dragging pans and a click without a drag plants.
const view = manager.view;
const zoomHud = document.querySelector("#zoom-hud");
const zoomLevel = document.querySelector("#zoom-level");
const zoomOut = document.querySelector("#zoom-out");
const zoomReset = document.querySelector("#zoom-reset");
const pointers = new Map();
let gesture = null;
const zoomable = () => manager.effectiveLook() === "sunlit";
function updateZoomHud() {
  const on = zoomable();
  zoomHud.hidden = !on;
  zoomLevel.textContent = `${view.zoom.toFixed(1)}×`;
  zoomOut.disabled = view.zoom <= 1.001;
  zoomReset.disabled = view.zoom <= 1.001;
  stage.canvas.classList.toggle("can-pan", on && view.zoom > 1.001);
}
function zoomBy(factor, x = stage.width / 2, y = stage.height / 2) {
  if (!zoomable()) return;
  view.zoomAt(x, y, factor);
  updateZoomHud();
  manager.requestFrame();
}
function plantAt(point) {
  const at = zoomable() ? view.toStage(point.x, point.y) : point;
  plant(selectedId, at.x, at.y);
}
function pinchState() {
  const [a, b] = [...pointers.values()];
  return { distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}
stage.canvas.addEventListener("pointerdown", event => {
  if (event.button !== 0 && event.pointerType === "mouse") return;
  stage.canvas.focus({ preventScroll: true });
  const point = stage.localPoint(event.clientX, event.clientY);
  if (!zoomable()) {
    plant(selectedId, point.x, point.y);
    return;
  }
  pointers.set(event.pointerId, point);
  try { stage.canvas.setPointerCapture(event.pointerId); } catch { /* pointer already gone */ }
  if (pointers.size === 2) {
    gesture = { mode: "pinch", ...pinchState() };
    return;
  }
  if (pointers.size > 2) return;
  // A mouse press on the unzoomed stage plants at once; touches wait to see if they pinch.
  if (view.zoom <= 1.001 && event.pointerType === "mouse") {
    plantAt(point);
    gesture = { mode: "done" };
    return;
  }
  gesture = { mode: "pending", x: point.x, y: point.y, lastX: point.x, lastY: point.y };
});
stage.canvas.addEventListener("pointermove", event => {
  if (!pointers.has(event.pointerId) || !gesture) return;
  const point = stage.localPoint(event.clientX, event.clientY);
  pointers.set(event.pointerId, point);
  if (gesture.mode === "pinch" && pointers.size >= 2) {
    const next = pinchState();
    view.zoomAt(next.x, next.y, next.distance / gesture.distance);
    view.panBy(next.x - gesture.x, next.y - gesture.y);
    gesture = { mode: "pinch", ...next };
  } else if (gesture.mode === "pending" || gesture.mode === "pan") {
    if (gesture.mode === "pending" && Math.hypot(point.x - gesture.x, point.y - gesture.y) > 6) {
      gesture.mode = view.zoom > 1.001 ? "pan" : "cancelled";
      if (gesture.mode === "pan") stage.canvas.classList.add("panning");
    }
    if (gesture.mode === "pan") view.panBy(point.x - gesture.lastX, point.y - gesture.lastY);
    gesture.lastX = point.x;
    gesture.lastY = point.y;
  } else {
    return;
  }
  updateZoomHud();
  manager.requestFrame();
});
function endPointer(event) {
  if (!pointers.has(event.pointerId)) return;
  pointers.delete(event.pointerId);
  if (gesture?.mode === "pending" && event.type === "pointerup") plantAt({ x: gesture.x, y: gesture.y });
  if (gesture?.mode === "pinch") gesture = pointers.size ? { mode: "cancelled" } : null;
  if (!pointers.size) gesture = null;
  stage.canvas.classList.remove("panning");
}
stage.canvas.addEventListener("pointerup", endPointer);
stage.canvas.addEventListener("pointercancel", endPointer);
stage.canvas.addEventListener("wheel", event => {
  if (!zoomable()) return;
  event.preventDefault();
  const point = stage.localPoint(event.clientX, event.clientY);
  const pixels = event.deltaY * (event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? stage.height : 1);
  zoomBy(Math.exp(-pixels * 0.0016), point.x, point.y);
}, { passive: false });
document.querySelector("#zoom-in").addEventListener("click", () => zoomBy(1.6));
zoomOut.addEventListener("click", () => zoomBy(1 / 1.6));
zoomReset.addEventListener("click", () => {
  view.reset();
  manager.requestFrame();
});
window.addEventListener("keydown", event => {
  if (event.target.closest?.("input, select, textarea") || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === "+" || event.key === "=") zoomBy(1.6);
  else if (event.key === "-" || event.key === "_") zoomBy(1 / 1.6);
  else if (event.key === "0" && zoomable()) {
    view.reset();
    manager.requestFrame();
  }
});
stage.canvas.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    const centre = zoomable() ? view.toStage(stage.width * 0.5, stage.height * 0.5) : { x: stage.width * 0.5, y: stage.height * 0.5 };
    plant(selectedId, centre.x, centre.y);
  }
});

showBackend(manager.backend);
const ready = manager.initialize().then(manifest => {
  // Draw the empty stage once so the Sunlit scene is visible before anything is planted.
  manager.requestFrame();
  return manifest;
});
if (debugEnabled) {
  window.__spun = {
    ready,
    settings,
    plant(id, x, y) { return plant(id, x, y); },
    seek(seconds) { manager.seek(seconds); },
    resume() { manager.resume(); },
    setBackend(value) { return manager.setBackend(value); },
    setMode(value) { const ok = manager.setMode(value); if (ok) ui.setMode(value); return ok; },
    setGlow(value) { for (const renderer of Object.values(renderers)) renderer.setGlow(value); manager.requestFrame(); },
    setSceneTime(seconds) { manager.sceneTime = Math.max(0, Number(seconds) || 0); manager.requestFrame(); },
    zoomTo(zoom, x, y) { view.animateTo(zoom, x, y); view.finish(); updateZoomHud(); manager.requestFrame(); },
    setDebugView(value) { if (glRenderer?.sunlit) glRenderer.sunlit.debugView = Number(value) || 0; manager.requestFrame(); },
    glContext() { return glRenderer?.gl ?? null; },
    clear() { manager.clear(); },
    stats() { return manager.stats(); },
    decoded(id) { return manager.decodedCounts(id); },
  };
}

if ("serviceWorker" in navigator) {
  if (query.get("nosw") === "1") {
    navigator.serviceWorker.getRegistrations()
      .then(registrations => Promise.all(registrations.map(registration => registration.unregister())))
      .catch(error => console.warn("Service worker cleanup failed.", error));
  } else {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(error => console.warn("Offline support unavailable.", error));
    }, { once: true });
  }
}

window.addEventListener("beforeunload", () => stage.destroy(), { once: true });
