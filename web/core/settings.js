// Scene settings: one schema drives the defaults, validation, persistence and the Scene panel.
// Light and air are kept per mode, so Dusk and Dawn each remember their own sun.

const STORAGE_KEY = "spun-scene";
const VERSION = 1;

export const MODES = ["dusk", "dawn"];

// Sun and atmosphere presets. sunX/sunY are stage fractions and may lie off the stage.
export const LIGHT_PRESETS = Object.freeze({
  golden: {
    label: "Golden hour",
    light: { sunX: 0.78, sunY: 0.12, backlight: 0.86, intensity: 1.1, sunColor: "#ffc27e", sunSize: 1.2 },
    air: { skyTop: "#2c3d5c", skyHorizon: "#e89a78", hazeColor: "#ffc0a0", haze: 0.38, rays: 1.1, rayLength: 0.7, ambient: 0.42, motes: 0.55 },
  },
  dawn: {
    label: "Misty dawn",
    light: { sunX: 0.16, sunY: -0.06, backlight: 0.78, intensity: 0.95, sunColor: "#ffdcae", sunSize: 1.5 },
    air: { skyTop: "#50668c", skyHorizon: "#e7cdb4", hazeColor: "#dfe3ea", haze: 0.8, rays: 0.95, rayLength: 0.8, ambient: 0.45, motes: 0.35 },
  },
  noon: {
    label: "Forest noon",
    light: { sunX: 0.56, sunY: -0.42, backlight: 0.62, intensity: 1.45, sunColor: "#fff3df", sunSize: 0.9 },
    air: { skyTop: "#6f9fd0", skyHorizon: "#cfe0cf", hazeColor: "#e6f1e2", haze: 0.3, rays: 0.7, rayLength: 0.55, ambient: 0.55, motes: 0.4 },
  },
  blue: {
    label: "Blue hour",
    light: { sunX: 0.08, sunY: 0.14, backlight: 0.9, intensity: 0.32, sunColor: "#ffab8a", sunSize: 2.2 },
    air: { skyTop: "#18223f", skyHorizon: "#4a5780", hazeColor: "#8d97c4", haze: 0.5, rays: 0.55, rayLength: 0.6, ambient: 0.55, motes: 0.2 },
  },
  moon: {
    label: "Moonlight",
    light: { sunX: 0.72, sunY: -0.08, backlight: 0.85, intensity: 0.14, sunColor: "#b4c6f0", sunSize: 0.8 },
    air: { skyTop: "#080b14", skyHorizon: "#1b2436", hazeColor: "#5e6c88", haze: 0.4, rays: 0.9, rayLength: 0.6, ambient: 0.55, motes: 0.1 },
  },
});

const MODE_PRESET = { dusk: "golden", dawn: "dawn" };

function modeDefaults(mode) {
  const preset = LIGHT_PRESETS[MODE_PRESET[mode]];
  return { preset: MODE_PRESET[mode], ...structuredClone(preset.light), ...structuredClone(preset.air) };
}

export const DEFAULTS = Object.freeze({
  version: VERSION,
  look: "sunlit",
  quality: "auto",
  motion: 0.55,
  light: { dusk: modeDefaults("dusk"), dawn: modeDefaults("dawn") },
  foliage: { density: 0.55, leafSize: 1, leafColor: "#5b8a4e", foreground: 0.6, blur: 0.65, bokeh: 0.7, bokehSize: 1, blades: 6, seed: 1 },
  silk: { brightness: 1, iridescence: 0.7, sheen: 0.45, thickness: 1, sparkle: 0.6 },
  dew: { when: "dawn", amount: 1, size: 1, refraction: 0.85, glint: 1, star: 6, speed: 1 },
  spiders: { model: "3d", size: 1, hair: 0.6, gloss: 0.6 },
  camera: { exposure: 0, contrast: 1.2, saturation: 1.1, warmth: 0, tone: 0.4, bloom: 0.8, vignette: 0.45, grain: 0.25, aberration: 0.25, flare: 0.35 },
});

// Panel schema. perMode groups live under light[mode]; root groups at the top level. Controls marked
// `both` also affect the Classic look; the rest only apply to Sunlit.
export const GROUPS = [
  {
    id: "light", label: "Sunlight", perMode: true, controls: [
      { key: "sun", type: "pad", label: "Sun position", x: "sunX", y: "sunY", min: -0.4, max: 1.4 },
      { key: "sunX", type: "range", label: "Sun across", min: -0.4, max: 1.4, step: 0.01, format: "percent" },
      { key: "sunY", type: "range", label: "Sun height", min: -0.4, max: 1.4, step: 0.01, format: "percent", invert: true },
      { key: "backlight", type: "range", label: "Backlight", min: 0, max: 1, step: 0.01, format: "percent", hint: "How squarely the sun shines through the web toward you" },
      { key: "intensity", type: "range", label: "Brightness", min: 0, max: 3, step: 0.01, format: "times" },
      { key: "sunSize", type: "range", label: "Softness", min: 0.3, max: 3, step: 0.01, format: "times", hint: "Size of the sun: softer dapples and wider glare" },
      { key: "sunColor", type: "color", label: "Sun colour" },
    ],
  },
  {
    id: "air", label: "Air & sky", perMode: true, controls: [
      { key: "rays", type: "range", label: "Light shafts", min: 0, max: 2, step: 0.01, format: "times" },
      { key: "rayLength", type: "range", label: "Shaft length", min: 0.1, max: 1, step: 0.01, format: "percent" },
      { key: "haze", type: "range", label: "Mist", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "ambient", type: "range", label: "Sky fill", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "motes", type: "range", label: "Floating motes", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "skyTop", type: "color", label: "Upper sky" },
      { key: "skyHorizon", type: "color", label: "Lower sky" },
      { key: "hazeColor", type: "color", label: "Mist colour" },
    ],
  },
  {
    id: "foliage", label: "Leaves & lens", controls: [
      { key: "density", type: "range", label: "Canopy", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "leafSize", type: "range", label: "Leaf size", min: 0.5, max: 2, step: 0.01, format: "times" },
      { key: "leafColor", type: "color", label: "Leaf colour" },
      { key: "foreground", type: "range", label: "Foreground leaves", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "blur", type: "range", label: "Depth of field", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "bokeh", type: "range", label: "Bokeh", min: 0, max: 1.5, step: 0.01, format: "times" },
      { key: "bokehSize", type: "range", label: "Bokeh size", min: 0.4, max: 2.5, step: 0.01, format: "times" },
      { key: "blades", type: "select", label: "Aperture", options: [[0, "Round"], [5, "5 blades"], [6, "6 blades"], [7, "7 blades"], [8, "8 blades"]] },
      { key: "seed", type: "seed", label: "Canopy" },
    ],
  },
  {
    id: "silk", label: "Silk", controls: [
      { key: "brightness", type: "range", label: "Brightness", min: 0, max: 3, step: 0.01, format: "times" },
      { key: "iridescence", type: "range", label: "Iridescence", min: 0, max: 1.5, step: 0.01, format: "times", hint: "Rainbow fringes where threads catch the sun" },
      { key: "sheen", type: "range", label: "Sheen width", min: 0.05, max: 1, step: 0.01, format: "percent" },
      { key: "thickness", type: "range", label: "Thickness", min: 0.5, max: 3, step: 0.01, format: "times" },
      { key: "sparkle", type: "range", label: "Glue sparkle", min: 0, max: 1.5, step: 0.01, format: "times", hint: "Glints from the glue droplets on capture silk" },
    ],
  },
  {
    id: "dew", label: "Dew", controls: [
      { key: "when", type: "select", label: "Dew forms", both: true, options: [["dawn", "At dawn"], ["always", "Always"], ["never", "Never"]] },
      { key: "amount", type: "range", label: "Amount", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "size", type: "range", label: "Droplet size", min: 0.4, max: 2.5, step: 0.01, format: "times" },
      { key: "refraction", type: "range", label: "Refraction", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "glint", type: "range", label: "Glints", min: 0, max: 3, step: 0.01, format: "times" },
      { key: "star", type: "select", label: "Star points", options: [[0, "None"], [4, "4-point"], [6, "6-point"], [8, "8-point"]] },
      { key: "speed", type: "range", label: "Condensing speed", both: true, min: 0.25, max: 4, step: 0.01, format: "times" },
    ],
  },
  {
    id: "spiders", label: "Spiders", controls: [
      { key: "model", type: "select", label: "Model", options: [["3d", "3-D, ray-marched"], ["glyph", "Illustrated"]] },
      { key: "size", type: "range", label: "Size", min: 0.5, max: 2, step: 0.01, format: "times" },
      { key: "hair", type: "range", label: "Hairiness", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "gloss", type: "range", label: "Gloss", min: 0, max: 1, step: 0.01, format: "percent" },
    ],
  },
  {
    id: "camera", label: "Camera", controls: [
      { key: "exposure", type: "range", label: "Exposure", min: -2, max: 2, step: 0.01, format: "ev" },
      { key: "contrast", type: "range", label: "Contrast", min: 0.5, max: 1.6, step: 0.01, format: "times" },
      { key: "saturation", type: "range", label: "Saturation", min: 0, max: 2, step: 0.01, format: "times" },
      { key: "warmth", type: "range", label: "Warmth", min: -1, max: 1, step: 0.01, format: "signed" },
      { key: "tone", type: "range", label: "Split tone", min: 0, max: 1, step: 0.01, format: "percent", hint: "Cools the shadows and warms the highlights" },
      { key: "bloom", type: "range", label: "Bloom", min: 0, max: 2, step: 0.01, format: "times" },
      { key: "flare", type: "range", label: "Lens flare", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "aberration", type: "range", label: "Chromatic fringe", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "vignette", type: "range", label: "Vignette", min: 0, max: 1, step: 0.01, format: "percent" },
      { key: "grain", type: "range", label: "Film grain", min: 0, max: 1, step: 0.01, format: "percent" },
    ],
  },
  {
    id: "render", label: "Rendering", root: true, controls: [
      { key: "look", type: "select", label: "Look", options: [["sunlit", "Sunlit (WebGL2)"], ["classic", "Classic"]] },
      { key: "quality", type: "select", label: "Quality", options: [["auto", "Automatic"], ["low", "Low"], ["medium", "Medium"], ["high", "High"], ["ultra", "Ultra"]] },
      { key: "motion", type: "range", label: "Breeze", min: 0, max: 1, step: 0.01, format: "percent", hint: "Leaves sway and light drifts; off lets the stage rest when webs are done" },
    ],
  },
];

const COLOR = /^#[0-9a-f]{6}$/i;

function controlIndex() {
  const index = new Map();
  for (const group of GROUPS) {
    for (const control of group.controls) {
      if (control.type === "pad") continue;
      index.set(`${group.perMode ? "light" : group.root ? "" : group.id}:${control.key}`, { group, control });
    }
  }
  return index;
}
const CONTROLS = controlIndex();

function sanitize(control, value, fallback) {
  if (control.type === "range" || control.type === "seed") {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    if (control.type === "seed") return Math.max(0, Math.min(0xffffffff, Math.round(number)));
    return Math.max(control.min, Math.min(control.max, number));
  }
  if (control.type === "color") return typeof value === "string" && COLOR.test(value) ? value.toLowerCase() : fallback;
  if (control.type === "select") {
    const match = control.options.find(([option]) => String(option) === String(value));
    return match ? match[0] : fallback;
  }
  return fallback;
}

// Rebuilds a full, valid settings object from any partial or stale input.
export function normalize(input) {
  const source = input && typeof input === "object" ? input : {};
  const out = structuredClone(DEFAULTS);
  for (const group of GROUPS) {
    for (const control of group.controls) {
      if (control.type === "pad") continue;
      if (group.perMode) {
        for (const mode of MODES) {
          const from = source.light?.[mode];
          if (from && control.key in from) out.light[mode][control.key] = sanitize(control, from[control.key], out.light[mode][control.key]);
        }
      } else if (group.root) {
        if (control.key in source) out[control.key] = sanitize(control, source[control.key], out[control.key]);
      } else {
        const from = source[group.id];
        if (from && control.key in from) out[group.id][control.key] = sanitize(control, from[control.key], out[group.id][control.key]);
      }
    }
  }
  for (const mode of MODES) {
    const preset = source.light?.[mode]?.preset;
    out.light[mode].preset = typeof preset === "string" && (preset in LIGHT_PRESETS || preset === "custom") ? preset : out.light[mode].preset;
  }
  return out;
}

function diff(value, base) {
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value)) {
      const d = diff(value[key], base?.[key]);
      if (d !== undefined) out[key] = d;
    }
    return Object.keys(out).length ? out : undefined;
  }
  return value === base ? undefined : value;
}

function toBase64Url(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(text) {
  const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder().decode(Uint8Array.from(binary, char => char.charCodeAt(0)));
}

export class SceneSettings {
  constructor({ storage = true } = {}) {
    this.storage = storage;
    this.listeners = new Set();
    this.values = normalize(this.readStored());
    this.saveTimer = 0;
    // A debounced save still pending when the page goes away is written at once.
    if (storage) window.addEventListener("pagehide", () => this.flush());
  }

  readStored() {
    if (!this.storage) return null;
    try {
      const text = localStorage.getItem(STORAGE_KEY);
      return text ? JSON.parse(text) : null;
    } catch {
      return null;
    }
  }

  save() {
    if (!this.storage) return;
    window.clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(() => this.flush(), 150);
  }

  flush() {
    if (!this.saveTimer) return;
    window.clearTimeout(this.saveTimer);
    this.saveTimer = 0;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(this.values)); } catch { /* storage unavailable */ }
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(change) {
    this.save();
    for (const listener of this.listeners) listener(this.values, change);
  }

  // path: "look", "silk.brightness", or "light.dawn.sunX".
  get(path) {
    return path.split(".").reduce((node, key) => node?.[key], this.values);
  }

  set(path, value) {
    const parts = path.split(".");
    const [head] = parts;
    let entry;
    if (head === "light") entry = CONTROLS.get(`light:${parts[2]}`);
    else if (parts.length === 1) entry = CONTROLS.get(`:${head}`);
    else entry = CONTROLS.get(`${head}:${parts[1]}`);
    if (!entry) return false;
    const target = parts.slice(0, -1).reduce((node, key) => node?.[key], this.values);
    const key = parts.at(-1);
    if (!target || !(key in target)) return false;
    const clean = sanitize(entry.control, value, target[key]);
    if (target[key] === clean) return true;
    target[key] = clean;
    if (head === "light") this.values.light[parts[1]].preset = "custom";
    this.emit({ path, value: clean });
    return true;
  }

  applyPreset(mode, id) {
    const preset = LIGHT_PRESETS[id];
    if (!preset || !MODES.includes(mode)) return false;
    this.values.light[mode] = { preset: id, ...structuredClone(preset.light), ...structuredClone(preset.air) };
    this.emit({ path: `light.${mode}`, preset: id });
    return true;
  }

  resetGroup(groupId, mode) {
    const group = GROUPS.find(item => item.id === groupId);
    if (!group) return;
    for (const control of group.controls) {
      if (control.type === "pad") continue;
      if (group.perMode) this.values.light[mode][control.key] = DEFAULTS.light[mode][control.key];
      else if (group.root) this.values[control.key] = DEFAULTS[control.key];
      else this.values[group.id][control.key] = DEFAULTS[group.id][control.key];
    }
    if (group.perMode) {
      const other = GROUPS.find(item => item.perMode && item.id !== groupId);
      const untouched = other.controls.every(control => control.type === "pad" ||
        this.values.light[mode][control.key] === DEFAULTS.light[mode][control.key]);
      this.values.light[mode].preset = untouched ? DEFAULTS.light[mode].preset : "custom";
    }
    this.emit({ path: groupId, reset: true });
  }

  resetAll() {
    this.values = structuredClone(DEFAULTS);
    this.values.light = { dusk: modeDefaults("dusk"), dawn: modeDefaults("dawn") };
    this.emit({ path: "", reset: true });
  }

  replace(values) {
    this.values = normalize(values);
    this.emit({ path: "", reset: true });
  }

  shareString() {
    return toBase64Url(JSON.stringify(diff(this.values, DEFAULTS) || {}));
  }

  applyShareString(text) {
    try {
      const partial = JSON.parse(fromBase64Url(text));
      const merged = structuredClone(DEFAULTS);
      const deepMerge = (into, from) => {
        for (const [key, value] of Object.entries(from || {})) {
          if (value && typeof value === "object" && into[key] && typeof into[key] === "object") deepMerge(into[key], value);
          else into[key] = value;
        }
      };
      deepMerge(merged, partial);
      this.replace(merged);
      return true;
    } catch {
      return false;
    }
  }

  // Dew condenses on finished webs in Dawn by default; the Dew group can make it always or never.
  dewWanted(mode) {
    const when = this.values.dew.when;
    return when === "always" || (when === "dawn" && mode === "dawn");
  }
}
