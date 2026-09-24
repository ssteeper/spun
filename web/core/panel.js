import { GROUPS, LIGHT_PRESETS } from "./settings.js";

const FORMATS = {
  percent: value => `${Math.round(value * 100)}%`,
  times: value => `${value.toFixed(2)}×`,
  ev: value => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)} EV`,
  signed: value => `${value >= 0 ? "+" : "−"}${Math.abs(Math.round(value * 100))}`,
};
const MODE_LABEL = { dusk: "Dusk", dawn: "Dawn" };
let uid = 0;

function element(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node && typeof value !== "string") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.filter(child => child != null));
  return node;
}

// Roving-tabindex radiogroup with arrow, Home and End keys (same pattern as the header groups).
function segmented(label, options, current, onChange, id) {
  const group = element("div", { class: "segments", role: "radiogroup", "aria-label": label, id });
  const buttons = options.map(([value, text]) => element("button", {
    class: "segment", type: "button", role: "radio", "data-value": String(value), text,
  }));
  const mark = value => {
    for (const button of buttons) {
      const on = button.dataset.value === String(value);
      button.setAttribute("aria-checked", String(on));
      button.tabIndex = on ? 0 : -1;
    }
  };
  const choose = (button, focus) => {
    if (!button || button.disabled) return;
    mark(button.dataset.value);
    onChange(options.find(([value]) => String(value) === button.dataset.value)[0]);
    if (focus) button.focus();
  };
  for (const button of buttons) {
    button.addEventListener("click", () => choose(button, false));
    button.addEventListener("keydown", event => {
      const live = buttons.filter(item => !item.disabled);
      const index = live.indexOf(button);
      const next = { ArrowRight: live[(index + 1) % live.length], ArrowDown: live[(index + 1) % live.length],
        ArrowLeft: live[(index - 1 + live.length) % live.length], ArrowUp: live[(index - 1 + live.length) % live.length],
        Home: live[0], End: live.at(-1) }[event.key];
      if (next) {
        event.preventDefault();
        choose(next, true);
      }
    });
  }
  group.append(...buttons);
  mark(current);
  return { group, buttons, mark };
}

export class ScenePanel {
  constructor({ panel, toggle, settings, getMode, backend }) {
    this.panel = panel;
    this.toggle = toggle;
    this.settings = settings;
    this.getMode = getMode;
    this.backend = backend; // { glAvailable(), sunlitAvailable(), current(), set(value) }
    this.bindings = [];
    this.build();
    toggle.addEventListener("click", () => this.setOpen(!this.isOpen()));
    panel.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.stopPropagation();
        this.setOpen(false);
        this.toggle.focus();
      }
    });
    settings.subscribe(() => this.refresh());
    window.addEventListener("resize", () => this.place(), { passive: true });
  }

  // The drawer starts below the header, whose height changes with the layout breakpoints.
  place() {
    const header = document.querySelector(".topbar");
    if (header) this.panel.style.setProperty("--panel-top", `${Math.round(header.getBoundingClientRect().bottom)}px`);
  }

  isOpen() {
    return !this.panel.hidden;
  }

  setOpen(open) {
    this.panel.hidden = !open;
    this.toggle.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("panel-open", open);
    if (open) {
      this.place();
      this.refresh();
      this.heading.focus({ preventScroll: true });
    }
  }

  path(group, key) {
    if (group.perMode) return `light.${this.getMode()}.${key}`;
    if (group.root) return key;
    return `${group.id}.${key}`;
  }

  build() {
    const panel = this.panel;
    panel.replaceChildren();
    this.heading = element("h2", { class: "panel-title", tabindex: "-1", text: "Scene" });
    const close = element("button", {
      class: "panel-close", type: "button", "aria-label": "Close scene settings",
      onclick: () => { this.setOpen(false); this.toggle.focus(); },
    });
    close.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9"/></svg>';
    this.modeNote = element("p", { class: "panel-note" });
    const header = element("div", { class: "panel-header" }, element("div", {}, this.heading, this.modeNote), close);

    this.look = segmented("Look", [["sunlit", "Sunlit"], ["classic", "Classic"]], this.settings.get("look"),
      value => this.settings.set("look", value), "look-group");
    this.lookNote = element("p", { class: "panel-hint", id: "look-note" });
    const lookRow = element("div", { class: "panel-look" }, this.look.group, this.lookNote);

    const presetLabel = element("p", { class: "panel-label", id: `presets-${++uid}` });
    this.presetLabel = presetLabel;
    this.presetButtons = Object.entries(LIGHT_PRESETS).map(([id, preset]) => element("button", {
      class: "preset", type: "button", "data-preset": id, text: preset.label,
      onclick: () => this.settings.applyPreset(this.getMode(), id),
    }));
    const presets = element("div", { class: "presets", role: "group", "aria-labelledby": presetLabel.id }, ...this.presetButtons);

    const body = element("div", { class: "panel-body" }, lookRow, element("div", { class: "preset-block sunlit-only" }, presetLabel, presets));
    for (const group of GROUPS) body.append(this.buildGroup(group));

    const share = element("button", { class: "panel-action", type: "button", text: "Copy share link", onclick: () => this.copyLink(share) });
    const reset = element("button", { class: "panel-action", type: "button", text: "Reset everything", onclick: () => this.settings.resetAll() });
    const footer = element("div", { class: "panel-footer" }, share, reset);
    panel.append(header, body, footer);
    this.refresh();
  }

  buildGroup(group) {
    const summaryId = `group-${group.id}`;
    const classicToo = group.root || group.controls.some(control => control.both);
    const details = element("details", { class: `panel-group${classicToo ? "" : " sunlit-only"}`, "data-group": group.id });
    if (["light", "render"].includes(group.id)) details.open = true;
    const resetGroup = element("button", {
      class: "group-reset", type: "button", text: "Reset", "aria-label": `Reset ${group.label}`,
      onclick: event => { event.preventDefault(); this.settings.resetGroup(group.id, this.getMode()); },
    });
    const summary = element("summary", { id: summaryId }, element("span", { text: group.label }), resetGroup);
    details.append(summary);
    const content = element("div", { class: "group-body" });
    for (const control of group.controls) {
      const row = this.buildControl(group, control);
      if (!row) continue;
      if (!group.root && !control.both) row.classList.add("sunlit-only");
      content.append(row);
    }
    if (group.id === "render") content.append(this.buildBackend());
    details.append(content);
    return details;
  }

  buildControl(group, control) {
    const id = `ctl-${group.id}-${control.key}`;
    if (control.type === "range") {
      const input = element("input", { type: "range", id, min: String(control.min), max: String(control.max), step: String(control.step) });
      const output = element("output", { for: id, class: "control-value" });
      const label = element("label", { for: id, text: control.label });
      if (control.hint) input.setAttribute("aria-describedby", `${id}-hint`);
      const row = element("div", { class: "control" },
        element("div", { class: "control-head" }, label, output), input,
        control.hint ? element("p", { class: "control-hint", id: `${id}-hint`, text: control.hint }) : null);
      const format = FORMATS[control.format] || (value => String(value));
      const show = value => {
        const shown = control.invert ? 1 - value : value;
        output.textContent = format(shown);
        input.setAttribute("aria-valuetext", output.textContent);
        const fraction = (value - control.min) / (control.max - control.min);
        input.style.setProperty("--fill", `${Math.max(0, Math.min(1, fraction)) * 100}%`);
      };
      input.addEventListener("input", () => {
        const value = Number(input.value);
        show(value);
        this.settings.set(this.path(group, control.key), value);
      });
      this.bindings.push(() => {
        const value = this.settings.get(this.path(group, control.key));
        if (Number(input.value) !== value) input.value = String(value);
        show(value);
      });
      return row;
    }
    if (control.type === "color") {
      const input = element("input", { type: "color", id });
      input.addEventListener("input", () => this.settings.set(this.path(group, control.key), input.value));
      this.bindings.push(() => { input.value = this.settings.get(this.path(group, control.key)); });
      return element("div", { class: "control control-color" }, element("label", { for: id, text: control.label }), input);
    }
    if (control.type === "select") {
      if (group.id === "render" && control.key === "look") return null; // shown at the top of the panel
      const labelId = `${id}-label`;
      const label = element("span", { class: "control-label", id: labelId, text: control.label });
      if (control.options.length <= 3) {
        const seg = segmented(control.label, control.options, this.settings.get(this.path(group, control.key)),
          value => this.settings.set(this.path(group, control.key), value), id);
        this.bindings.push(() => seg.mark(this.settings.get(this.path(group, control.key))));
        return element("div", { class: "control control-inline" }, label, seg.group);
      }
      const select = element("select", { id, "aria-labelledby": labelId });
      for (const [value, text] of control.options) select.append(element("option", { value: String(value), text }));
      select.addEventListener("change", () => {
        const option = control.options.find(([value]) => String(value) === select.value);
        if (option) this.settings.set(this.path(group, control.key), option[0]);
      });
      this.bindings.push(() => { select.value = String(this.settings.get(this.path(group, control.key))); });
      return element("div", { class: "control control-inline" }, label, select);
    }
    if (control.type === "seed") {
      const value = element("span", { class: "control-value" });
      const button = element("button", {
        class: "panel-action small", type: "button", text: "Grow new leaves",
        onclick: () => this.settings.set(this.path(group, control.key), (Math.random() * 0xffffffff) >>> 0),
      });
      this.bindings.push(() => { value.textContent = `#${this.settings.get(this.path(group, control.key)) % 100000}`; });
      return element("div", { class: "control control-inline" }, element("span", { class: "control-label", text: control.label }), value, button);
    }
    if (control.type === "pad") return this.buildPad(group, control);
    return null;
  }

  // A pointer shortcut for the two sun sliders; keyboard users use the sliders it mirrors.
  buildPad(group, control) {
    const pad = element("div", { class: "sun-pad", "aria-hidden": "true" });
    const frame = element("div", { class: "sun-pad-stage" });
    const dot = element("div", { class: "sun-pad-dot" });
    pad.append(frame, dot);
    const span = control.max - control.min;
    const place = () => {
      const x = this.settings.get(this.path(group, control.x));
      const y = this.settings.get(this.path(group, control.y));
      dot.style.left = `${((x - control.min) / span) * 100}%`;
      dot.style.top = `${((y - control.min) / span) * 100}%`;
      pad.style.setProperty("--sun-x", dot.style.left);
      pad.style.setProperty("--sun-y", dot.style.top);
    };
    const move = event => {
      const rect = pad.getBoundingClientRect();
      const x = control.min + span * Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const y = control.min + span * Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
      this.settings.set(this.path(group, control.x), Math.round(x * 100) / 100);
      this.settings.set(this.path(group, control.y), Math.round(y * 100) / 100);
    };
    pad.addEventListener("pointerdown", event => {
      pad.setPointerCapture(event.pointerId);
      move(event);
    });
    pad.addEventListener("pointermove", event => {
      if (pad.hasPointerCapture(event.pointerId)) move(event);
    });
    this.bindings.push(place);
    return element("div", { class: "control" }, element("span", { class: "control-label", text: control.label }), pad);
  }

  buildBackend() {
    const options = [["gl", "WebGL2"], ["2d", "Canvas 2D"]];
    this.backendSeg = segmented("Renderer", options, this.backend.current(), value => this.backend.set(value), "backend-group");
    this.backendSeg.group.classList.add("backend-segments");
    return element("div", { class: "control control-inline" }, element("span", { class: "control-label", text: "Renderer" }), this.backendSeg.group);
  }

  setBackendState(glAvailable, backend) {
    if (!this.backendSeg) return;
    const gl = this.backendSeg.buttons.find(button => button.dataset.value === "gl");
    gl.disabled = !glAvailable;
    this.backendSeg.mark(backend);
    this.refresh();
  }

  async copyLink(button) {
    const url = new URL(location.href);
    url.hash = `scene=${this.settings.shareString()}`;
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(url.href);
      button.textContent = "Link copied";
    } catch {
      history.replaceState(null, "", url.href);
      button.textContent = "Link is in the address bar";
    }
    window.setTimeout(() => { button.textContent = original; }, 1800);
  }

  refresh() {
    const mode = this.getMode();
    const values = this.settings.values;
    const onGl = this.backend.current() === "gl";
    const sunlitPossible = onGl && this.backend.sunlitAvailable();
    const sunlit = values.look === "sunlit" && sunlitPossible;
    this.panel.classList.toggle("is-classic", !sunlit);
    this.look.mark(sunlit ? "sunlit" : "classic");
    const sunlitButton = this.look.buttons.find(button => button.dataset.value === "sunlit");
    sunlitButton.disabled = !sunlitPossible;
    let note = sunlit ? "Ray-marched sunlight, dew and 3-D spiders." : "The original line-drawn plates.";
    if (!this.backend.glAvailable()) note = "Sunlit needs WebGL2, which this browser lacks; Classic is shown.";
    else if (!onGl) note = "Sunlit draws with the WebGL2 renderer (below); Canvas 2D shows Classic.";
    else if (!sunlitPossible) note = "Sunlit needs floating-point render targets, which this GPU lacks; Classic is shown.";
    this.lookNote.textContent = note;
    this.modeNote.textContent = `Light for ${MODE_LABEL[mode]} · switch mode in the header`;
    this.presetLabel.textContent = `${MODE_LABEL[mode]} light`;
    const active = values.light[mode].preset;
    for (const button of this.presetButtons) button.setAttribute("aria-pressed", String(button.dataset.preset === active));
    for (const bind of this.bindings) bind();
    if (this.backendSeg) this.backendSeg.mark(this.backend.current());
  }
}
