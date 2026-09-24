function makeRadioGroup(element, onChange) {
  const buttons = [...element.querySelectorAll('[role="radio"]')];
  const enabled = () => buttons.filter(button => !button.disabled);
  function mark(button) {
    for (const option of buttons) {
      const selected = option === button;
      option.setAttribute("aria-checked", String(selected));
      option.tabIndex = selected ? 0 : -1;
    }
  }
  function select(button, focus = false) {
    if (!button || button.disabled) return;
    mark(button);
    onChange(button.dataset.value);
    if (focus) button.focus();
  }
  for (const button of buttons) {
    button.addEventListener("click", () => select(button));
    button.addEventListener("keydown", event => {
      const choices = enabled();
      const index = choices.indexOf(button);
      let next = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = choices[(index + 1) % choices.length];
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = choices[(index - 1 + choices.length) % choices.length];
      else if (event.key === "Home") next = choices[0];
      else if (event.key === "End") next = choices.at(-1);
      if (next) {
        event.preventDefault();
        select(next, true);
      }
    });
  }
  return { select, mark, buttons };
}

function commonName(name) {
  return String(name || "").replace(/\s+/g, " ").trim();
}
const CHIP_LABELS = Object.freeze({
  "golden-orb-weaver": "Golden Orb",
  "st-andrews-cross": "St Andrew's",
  "garden-orb-weaver": "Garden Orb",
  "leaf-curling-spider": "Leaf-curling",
  "christmas-jewel-spider": "Christmas",
  "scorpion-tailed-spider": "Scorpion-tail",
  "net-casting-spider": "Net-casting",
  "magnificent-spider": "Magnificent",
  "redback-spider": "Redback",
});

export class ViewerUI {
  constructor({ rows, status, liveStatus, stageHint, clearButton, modeGroup, backendGroup }, { onSelect, onClear, onBackend = () => {}, onMode = () => {} }) {
    this.rows = rows;
    this.status = status;
    this.liveStatus = liveStatus;
    this.stageHint = stageHint;
    this.onSelect = onSelect;
    this.selectedId = null;
    this.lastLiveAt = -Infinity;
    this.lastLiveLabel = null;
    this.pendingLive = null;
    this.liveTimer = 0;
    clearButton.addEventListener("click", onClear);
    this.modeGroup = makeRadioGroup(modeGroup, value => onMode(value));
    this.backendGroup = makeRadioGroup(backendGroup, value => onBackend(value));
    window.addEventListener("keydown", event => {
      if (event.key === "Escape") onClear();
    });
  }

  setMode(mode) {
    this.modeGroup.mark(this.modeGroup.buttons.find(button => button.dataset.value === mode));
  }

  setBackendState(glAvailable, backend) {
    const buttons = this.backendGroup.buttons;
    const gl = buttons.find(button => button.dataset.value === "gl");
    gl.disabled = !glAvailable;
    this.backendGroup.mark(buttons.find(button => button.dataset.value === backend) || buttons[0]);
  }

  renderSpecimens(specimens, selectedId) {
    this.rows.replaceChildren();
    const categories = [
      ["orb", "Orbs"],
      ["snare", "Snares"],
    ];
    for (const [kind, label] of categories) {
      const row = document.createElement("div");
      row.className = "species-row";
      const rowLabel = document.createElement("span");
      rowLabel.className = "row-label";
      rowLabel.textContent = label;
      row.append(rowLabel);
      const group = document.createElement("div");
      group.className = "species-chips";
      const options = specimens.filter(specimen => specimen.kind === kind);
      for (const specimen of options) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "chip";
        button.setAttribute("role", "radio");
        button.setAttribute("aria-checked", String(specimen.id === selectedId));
        button.tabIndex = specimen.id === selectedId ? 0 : -1;
        button.dataset.specimen = specimen.id;
        button.textContent = CHIP_LABELS[specimen.id] || commonName(specimen.name);
        button.setAttribute("aria-label", commonName(specimen.name));
        button.title = specimen.scientific ? `${specimen.name} · ${specimen.scientific}` : specimen.name;
        button.addEventListener("click", () => this.selectSpecimen(specimen.id, false));
        button.addEventListener("keydown", event => {
          const buttons = [...this.rows.querySelectorAll('[role="radio"]')];
          const index = buttons.indexOf(button);
          let next = null;
          if (event.key === "ArrowRight" || event.key === "ArrowDown") next = buttons[(index + 1) % buttons.length];
          else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = buttons[(index - 1 + buttons.length) % buttons.length];
          else if (event.key === "Home") next = buttons[0];
          else if (event.key === "End") next = buttons.at(-1);
          if (next) {
            event.preventDefault();
            this.selectSpecimen(next.dataset.specimen, true);
          }
        });
        group.append(button);
      }
      row.append(group);
      this.rows.append(row);
    }
    this.selectedId = selectedId;
  }

  selectSpecimen(id, focus = false) {
    this.selectedId = id;
    const buttons = [...this.rows.querySelectorAll('[role="radio"]')];
    const target = buttons.find(button => button.dataset.specimen === id);
    if (!target) return;
    for (const button of buttons) {
      const selected = button === target;
      button.setAttribute("aria-checked", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }
    if (focus) target.focus();
    this.onSelect(id);
  }

  setStatus(specimen, label, cursor, data, instanceCount) {
    if (!specimen || !data) return;
    const done = cursor >= data.count;
    const progress = done ? `${Number(specimen.silkMetres || 0).toFixed(1)} m of silk` : `${instanceCount} / 12 spun`;
    const text = `${commonName(specimen.name)} · ${label} · ${progress}`;
    if (this.status.textContent !== text) this.status.textContent = text;
    this.hideStageHint();
    if (label === this.pendingLive?.label) return;
    if (label === this.lastLiveLabel) {
      this.cancelPendingLive();
      return;
    }
    const delay = 1000 - (performance.now() - this.lastLiveAt);
    if (delay <= 0) {
      this.announceLive(text, label);
      return;
    }
    this.pendingLive = { text, label };
    if (!this.liveTimer) this.liveTimer = window.setTimeout(() => this.flushLive(), delay);
  }

  announceLive(text, label) {
    this.cancelPendingLive();
    this.liveStatus.textContent = text;
    this.lastLiveAt = performance.now();
    this.lastLiveLabel = label;
  }

  flushLive() {
    this.liveTimer = 0;
    if (!this.pendingLive) return;
    const { text, label } = this.pendingLive;
    this.pendingLive = null;
    this.liveStatus.textContent = text;
    this.lastLiveAt = performance.now();
    this.lastLiveLabel = label;
  }

  cancelPendingLive() {
    if (this.liveTimer) window.clearTimeout(this.liveTimer);
    this.liveTimer = 0;
    this.pendingLive = null;
  }

  hideStageHint() {
    this.stageHint.classList.add("hidden");
  }

  resetStatus() {
    this.cancelPendingLive();
    this.lastLiveLabel = null;
    this.status.textContent = "Choose a web, then plant it on the stage.";
    this.stageHint.classList.remove("hidden");
  }

  clear() {
    this.resetStatus();
  }
}
