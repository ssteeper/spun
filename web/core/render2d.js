import { minLod } from "../silk.js";

const FLAG_INVISIBLE = 1 << 2;
const BEAD_GLUE = 2;

function makeCanvas(width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, width);
  canvas.height = Math.max(1, height);
  return canvas;
}

function lodVisible(data, index, threshold) {
  return data.styles[index * 8 + 5] >= threshold;
}

function opacityAt(data, index, cursor, fadeRecords) {
  const death = data.deaths[index];
  if (death === 0xffffffff || cursor < death) return 1;
  const fade = Math.min(fadeRecords, data.count - death);
  return Math.max(0, 1 - (cursor - death) / Math.max(1, fade));
}

export class Renderer2D {
  constructor(stage, stageConfig) {
    this.stage = stage;
    this.stageConfig = stageConfig;
    this.ctx = stage.ctx;
    this.glowEnabled = true;
    this.recordsDrawnLastFrame = 0;
    this.beadsDrawnLastFrame = 0;
    this.temporaryRecordsDrawnLastFrame = 0;
    this.glBufferUploadsLastFrame = null;
    this.glBufferUploadsTotal = null;
  }

  setGlow(enabled) {
    this.glowEnabled = Boolean(enabled);
  }

  render(instances) {
    const ctx = this.ctx;
    const { width, height } = this.stage;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#05060c";
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
    this.recordsDrawnLastFrame = 0;
    this.beadsDrawnLastFrame = 0;
    this.temporaryRecordsDrawnLastFrame = 0;
    for (const instance of instances) {
      if (!instance.buffers || instance.buffers.invalid) this.createBuffers(instance);
      this.updatePermanent(instance);
      this.drawDynamic(instance);
      const rect = instance.placement.screenBounds;
      ctx.drawImage(instance.buffers.permanent, rect.left, rect.top, rect.width, rect.height);
      ctx.drawImage(instance.buffers.dynamic, rect.left, rect.top, rect.width, rect.height);
    }
    if (!this.glowEnabled) return;
    for (const instance of instances) {
      if (!instance.buffers.glowUsable) continue;
      this.updateGlow(instance);
      const rect = instance.placement.screenBounds;
      const pad = instance.buffers.glowPad * 2 / this.stage.dpr;
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = (this.stageConfig?.glow?.strength ?? 0.5) * (instance.mode === "dawn" ? 1.2 : 1);
      ctx.drawImage(instance.buffers.glow, rect.left - pad, rect.top - pad, rect.width + pad * 2, rect.height + pad * 2);
      ctx.restore();
    }
  }

  createBuffers(instance) {
    const { dpr } = this.stage;
    const rect = instance.placement.screenBounds;
    const pixelWidth = Math.max(1, Math.ceil(rect.width * dpr));
    const pixelHeight = Math.max(1, Math.ceil(rect.height * dpr));
    const glowWidth = Math.ceil(pixelWidth / 2);
    const glowHeight = Math.ceil(pixelHeight / 2);
    const radius = this.stageConfig?.glow?.radius ?? 14;
    const glowPad = Math.ceil(3 * radius * 0.5 * dpr);
    const permanent = makeCanvas(pixelWidth, pixelHeight);
    const dynamic = makeCanvas(pixelWidth, pixelHeight);
    const combined = makeCanvas(pixelWidth, pixelHeight);
    const glow = makeCanvas(glowWidth + glowPad * 2, glowHeight + glowPad * 2);
    const permanentCtx = permanent.getContext("2d");
    const dynamicCtx = dynamic.getContext("2d");
    const combinedCtx = combined.getContext("2d");
    const glowCtx = glow.getContext("2d");
    const linear = instance.placement.scale * dpr;
    const tx = (instance.placement.originX - rect.left) * dpr;
    const ty = (instance.placement.originY - rect.top) * dpr;
    for (const layerCtx of [permanentCtx, dynamicCtx]) layerCtx.setTransform(linear, 0, 0, linear, tx, ty);
    combinedCtx.setTransform(1, 0, 0, 1, 0, 0);
    glowCtx.setTransform(1, 0, 0, 1, 0, 0);
    instance.buffers = {
      permanent, dynamic, combined, glow,
      permanentCtx, dynamicCtx, combinedCtx, glowCtx,
      builtThrough: -1,
      dynamicCursor: NaN,
      glowUsable: "filter" in glowCtx,
      glowCursor: NaN,
      glowPad,
      glowWidth,
      glowHeight,
      invalid: false,
    };
  }


  invalidate(instance) {
    if (instance.buffers) instance.buffers.invalid = true;
  }

  updatePermanent(instance) {
    const { data, cursor, buffers } = instance;
    const ctx = buffers.permanentCtx;
    const complete = Math.min(data.count - 1, Math.floor(cursor) - 1);
    if (complete < buffers.builtThrough) {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, buffers.permanent.width, buffers.permanent.height);
      ctx.restore();
      buffers.builtThrough = -1;
    }
    const threshold = minLod(instance.placement.detail);
    for (let i = buffers.builtThrough + 1; i <= complete; i++) {
      const offset = i * 8;
      const flags = data.styles[offset + 6];
      const death = data.deaths[i];
      if (death !== 0xffffffff || (flags & FLAG_INVISIBLE)) continue;
      if (!lodVisible(data, i, threshold)) continue;
      this.strokeRecord(ctx, data, i, 1, instance.placement.scale);
      this.recordsDrawnLastFrame++;
      for (let b = data.beadStart[i]; b < data.beadEnd[i]; b++) {
        if (!(data.beadFlags[b] & BEAD_GLUE)) continue;
        if (this.drawBead(ctx, instance, b, 1)) this.beadsDrawnLastFrame++;
      }
    }
    buffers.builtThrough = Math.max(buffers.builtThrough, complete);
  }

  // Dynamic layer: live/fading temporaries plus the tip, redrawn only when the cursor moves.
  drawDynamic(instance) {
    const { data, cursor, buffers } = instance;
    if (buffers.dynamicCursor === cursor) return;
    const ctx = buffers.dynamicCtx;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, buffers.dynamic.width, buffers.dynamic.height);
    ctx.restore();
    const threshold = minLod(instance.placement.detail);
    const scale = instance.placement.scale;
    const fadeRecords = instance.specimen.fadeRecords || 6;
    const completed = Math.min(data.count, Math.floor(cursor));
    for (let n = 0; n < data.temporary.length; n++) {
      const i = data.temporary[n];
      if (i >= completed) continue;
      if ((data.styles[i * 8 + 6] & FLAG_INVISIBLE) || !lodVisible(data, i, threshold)) continue;
      const alpha = opacityAt(data, i, cursor, fadeRecords);
      if (alpha <= 0) continue;
      this.strokeRecord(ctx, data, i, alpha, scale);
      this.recordsDrawnLastFrame++;
      this.temporaryRecordsDrawnLastFrame++;
      for (let b = data.beadStart[i]; b < data.beadEnd[i]; b++) {
        if (!(data.beadFlags[b] & BEAD_GLUE)) continue;
        if (this.drawBead(ctx, instance, b, 1, alpha)) this.beadsDrawnLastFrame++;
      }
    }
    const fraction = cursor - completed;
    if (completed < data.count && fraction > 0) {
      const flags = data.styles[completed * 8 + 6];
      if (!(flags & FLAG_INVISIBLE) && lodVisible(data, completed, threshold)) {
        const alpha = opacityAt(data, completed, cursor, fadeRecords);
        this.strokeRecord(ctx, data, completed, alpha, scale, fraction);
        this.recordsDrawnLastFrame++;
        if (data.deaths[completed] !== 0xffffffff) this.temporaryRecordsDrawnLastFrame++;
      }
    }
    buffers.dynamicCursor = cursor;
    buffers.glowCursor = NaN;
  }

  strokeRecord(ctx, data, index, alpha, scale, fraction = 1) {
    const coordinate = index * 4;
    const x0 = data.coords[coordinate];
    const y0 = data.coords[coordinate + 1];
    const x1 = data.coords[coordinate] + (data.coords[coordinate + 2] - data.coords[coordinate]) * fraction;
    const y1 = data.coords[coordinate + 1] + (data.coords[coordinate + 3] - data.coords[coordinate + 1]) * fraction;
    const nativeWidth = data.widths[index];
    const deviceWidth = Math.max(nativeWidth * scale, 0.55) * this.stage.dpr;
    const alphaCoverage = Math.min(deviceWidth, 1);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha * data.alphas[index] * alphaCoverage));
    ctx.strokeStyle = data.colors[index];
    ctx.lineWidth = Math.max(deviceWidth, 1) / (this.stage.dpr * scale);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.restore();
  }

  drawBead(ctx, instance, index, progress, recordAlpha = 1) {
    const data = instance.data;
    const radius = data.beadRadii[index] * instance.placement.scale;
    if (radius <= 0) return false;
    const x = data.beadX[index];
    const y = data.beadY[index];
    const host = data.beadHosts[index];
    const color = data.colors[host];
    const alpha = data.alphas[host];
    const r = radius * progress;
    if (r <= 0) return false;
    ctx.save();
    ctx.globalAlpha = alpha * recordAlpha * 0.35;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = alpha * recordAlpha * 0.85;
    ctx.strokeStyle = "rgba(255,255,255,.86)";
    ctx.lineWidth = Math.max(0.35 / this.stage.dpr, r * 0.12);
    ctx.beginPath();
    ctx.arc(x, y, r * 0.85, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = alpha * recordAlpha;
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(x - r * 0.35, y - r * 0.35, Math.max(0.2, r * 0.28), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    return true;
  }

  updateGlow(instance) {
    const buffers = instance.buffers;
    if (buffers.glowCursor === instance.cursor) return;
    const { combinedCtx, combined, glowCtx, glow, glowPad, glowWidth, glowHeight } = buffers;
    combinedCtx.clearRect(0, 0, combined.width, combined.height);
    combinedCtx.drawImage(buffers.permanent, 0, 0);
    combinedCtx.drawImage(buffers.dynamic, 0, 0);
    glowCtx.save();
    glowCtx.setTransform(1, 0, 0, 1, 0, 0);
    glowCtx.clearRect(0, 0, glow.width, glow.height);
    const radius = this.stageConfig?.glow?.radius ?? 14;
    glowCtx.filter = `blur(${radius * 0.5 * this.stage.dpr}px)`;
    glowCtx.drawImage(combined, 0, 0, combined.width, combined.height, glowPad, glowPad, glowWidth, glowHeight);
    glowCtx.restore();
    buffers.glowCursor = instance.cursor;
  }
}
