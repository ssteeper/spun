import { activeSpiders } from "./spiderPose.js";

function hexColor(value) {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : "#dbe5f1";
}

export class SpiderOverlay {
  constructor(stage) {
    this.stage = stage;
    this.ctx = stage.overlayCtx;
    this.enabled = true; // false while the Sunlit renderer draws the 3-D spiders itself
    this.view = null;    // the Sunlit zoom, when the illustrated spiders are drawn over it
  }

  draw(instances) {
    const { ctx, stage } = this;
    ctx.clearRect(0, 0, stage.width, stage.height);
    if (!this.enabled) return;
    const view = this.view && !this.view.identity ? this.view : null;
    if (view) ctx.setTransform(stage.dpr * view.zoom, 0, 0, stage.dpr * view.zoom, stage.dpr * view.tx, stage.dpr * view.ty);
    for (const { spider, fade, settling, pose } of activeSpiders(instances)) {
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.translate(pose.x, pose.y);
      ctx.rotate(pose.angle);
      this.drawGlyph(spider.glyph, pose, settling);
      ctx.restore();
    }
    if (view) ctx.setTransform(stage.dpr, 0, 0, stage.dpr, 0, 0);
  }

  drawGlyph(glyph, pose, settling) {
    const ctx = this.ctx;
    const scale = pose.scale;
    const restVisible = pose.restVisible;
    const liveLegs = pose.gaitLegs || pose.restLegs;
    const restLegs = pose.restLegs || liveLegs;
    const firstJoint = pose.isRest ? Math.max(0, Math.min(3, restVisible.legFromJoint | 0)) : 0;
    const interpolate = (a, b) => a + (b - a) * settling;
    const strokeSegment = (from, to, width, color) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(0.2, width * scale);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(from[0] * scale, from[1] * scale);
      ctx.lineTo(to[0] * scale, to[1] * scale);
      ctx.stroke();
    };
    const legStyle = glyph.legs || {};
    const widths = Array.isArray(legStyle.width) ? legStyle.width : [0.8, 0.6, 0.4];
    const legColor = hexColor(legStyle.color);
    const bandColor = legStyle.band ? hexColor(legStyle.band) : null;
    for (let leg = 0; leg < 8; leg++) {
      for (let segment = 0; segment < 3; segment++) {
        const segmentAlpha = pose.isRest && segment < firstJoint ? 1 - settling : 1;
        if (segmentAlpha <= 0) continue;
        const movingFrom = liveLegs[leg]?.[segment] || [0, 0];
        const movingTo = liveLegs[leg]?.[segment + 1] || movingFrom;
        const restFrom = restLegs?.[leg]?.[segment] || movingFrom;
        const restTo = restLegs?.[leg]?.[segment + 1] || movingTo;
        const from = [interpolate(movingFrom[0], restFrom[0]), interpolate(movingFrom[1], restFrom[1])];
        const to = [interpolate(movingTo[0], restTo[0]), interpolate(movingTo[1], restTo[1])];
        const width = widths[segment] ?? widths.at(-1) ?? 0.5;
        ctx.save();
        ctx.globalAlpha *= segmentAlpha;
        strokeSegment(from, to, width, legColor);
        if (bandColor && segment >= 1) {
          const start = [from[0] + (to[0] - from[0]) / 3, from[1] + (to[1] - from[1]) / 3];
          const end = [from[0] + (to[0] - from[0]) * 2 / 3, from[1] + (to[1] - from[1]) * 2 / 3];
          strokeSegment(start, end, width, bandColor);
        }
        ctx.restore();
      }
    }
    const bodyAlpha = pose.isRest && !restVisible.body ? 1 - settling : 1;
    for (const shape of glyph.body || []) this.drawShape(shape, scale, bodyAlpha);
    const eyeAlpha = pose.isRest && !restVisible.eyes ? 1 - settling : 1;
    for (const eye of glyph.eyes || []) {
      this.drawCircle(eye.x * scale, eye.y * scale, eye.r * scale, hexColor(eye.fill), eyeAlpha);
      if (eye.glint) this.drawCircle(eye.glint.x * scale, eye.glint.y * scale, eye.glint.r * scale, "#ffffff", eyeAlpha);
    }
  }

  drawShape(shape, scale, alpha) {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha *= Math.max(0, Math.min(1, alpha * (shape.alpha ?? 1)));
    ctx.fillStyle = shape.fill ? hexColor(shape.fill) : "transparent";
    ctx.strokeStyle = shape.stroke ? hexColor(shape.stroke) : "transparent";
    ctx.lineWidth = Math.max(0.2, (shape.lw || 0) * scale);
    if (shape.type === "ellipse") {
      ctx.translate(shape.x * scale, shape.y * scale);
      ctx.rotate(shape.rot || 0);
      ctx.beginPath();
      ctx.ellipse(0, 0, Math.max(0.1, shape.rx * scale), Math.max(0.1, shape.ry * scale), 0, 0, Math.PI * 2);
    } else if (shape.type === "polygon" && Array.isArray(shape.points) && shape.points.length) {
      ctx.beginPath();
      ctx.moveTo(shape.points[0][0] * scale, shape.points[0][1] * scale);
      for (let i = 1; i < shape.points.length; i++) ctx.lineTo(shape.points[i][0] * scale, shape.points[i][1] * scale);
      ctx.closePath();
    } else {
      ctx.restore();
      return;
    }
    if (shape.fill) ctx.fill();
    if (shape.stroke && shape.lw > 0) ctx.stroke();
    ctx.restore();
  }

  drawCircle(x, y, radius, fill, alpha) {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(0.15, radius), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}
