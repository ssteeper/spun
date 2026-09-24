const REST_SECONDS = 0.5;
const FADE_IN_SECONDS = 0.3;

function hexColor(value) {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : "#dbe5f1";
}

export class SpiderOverlay {
  constructor(stage) {
    this.stage = stage;
    this.ctx = stage.overlayCtx;
    this.enabled = true; // false while the Sunlit renderer draws the 3-D spiders itself
  }

  draw(instances) {
    const { ctx, stage } = this;
    ctx.clearRect(0, 0, stage.width, stage.height);
    if (!this.enabled) return;
    for (const instance of instances) {
      const data = instance.data;
      const spiders = data.specimen.spiders || [];
      for (const spider of spiders) {
        const builder = spider.builder;
        const first = instance.builderFirst[builder];
        const last = instance.builderLast[builder];
        if (first == null || instance.cursor <= first) continue;
        const fade = instance.reducedMotion ? 1 : Math.max(0, Math.min(1, (instance.elapsed - instance.builderStartSeconds[builder]) / FADE_IN_SECONDS));
        if (fade <= 0) continue;
        const completed = instance.cursor >= last + 1;
        const settling = completed ? Math.max(0, Math.min(1, (instance.elapsed - instance.builderFinishSeconds[builder]) / REST_SECONDS)) : 0;
        const pose = this.spiderPose(instance, spider, builder, completed, settling);
        if (!pose) continue;
        ctx.save();
        ctx.globalAlpha = fade;
        ctx.translate(pose.x, pose.y);
        ctx.rotate(pose.angle);
        this.drawGlyph(spider.glyph, pose, settling);
        ctx.restore();
      }
    }
  }

  spiderPose(instance, spider, builder, completed, settling) {
    const data = instance.data;
    const specimen = data.specimen;
    const first = instance.builderFirst[builder];
    const last = instance.builderLast[builder];
    if (first == null || last == null) return null;
    let record = Math.min(data.count - 1, Math.max(first, Math.floor(instance.cursor)));
    while (record > first && ((data.styles[record * 8 + 6] >> 4) & 3) !== builder) record--;
    const local = completed ? 1 : Math.max(0, Math.min(1, instance.cursor - record));
    const p = record * 4;
    const x = data.coords[p] + (data.coords[p + 2] - data.coords[p]) * local;
    const y = data.coords[p + 1] + (data.coords[p + 3] - data.coords[p + 1]) * local;
    const angle = Math.atan2(data.coords[p + 3] - data.coords[p + 1], data.coords[p + 2] - data.coords[p]);
    const placement = instance.placement;
    const { originX, originY } = placement;
    const distanceEnd = data.cumulativeLength[record];
    const distance = completed ? data.builderLengths[builder] : distanceEnd - data.lengths[record] + data.lengths[record] * local;
    const glyph = spider.glyph;
    const mmPerUnit = specimen.mmPerUnit || 1;
    const phase = ((distance * mmPerUnit / Math.max(1e-6, glyph.strideMm || 1)) % 1 + 1) % 1 * 8;
    const frame = Math.floor(phase) % 8;
    const fraction = phase - Math.floor(phase);
    const gait = glyph.gait || [];
    const gaitLegs = gait.length === 8 ? gait[frame].map((leg, legIndex) => leg.map((joint, jointIndex) => [
      joint[0] + (gait[(frame + 1) % 8][legIndex][jointIndex][0] - joint[0]) * fraction,
      joint[1] + (gait[(frame + 1) % 8][legIndex][jointIndex][1] - joint[1]) * fraction,
    ])) : glyph.rest;
    const restAngle = spider.rest?.angle ?? angle;
    const angleDelta = Math.atan2(Math.sin(restAngle - angle), Math.cos(restAngle - angle));
    return {
      x: originX + x * placement.scale,
      y: originY + y * placement.scale,
      angle: angle + angleDelta * settling,
      gaitLegs,
      restLegs: glyph.rest,
      scale: placement.scale * (glyph.scale || 1) / mmPerUnit,
      isRest: completed,
      restVisible: glyph.restVisible || { body: true, eyes: true, legFromJoint: 0 },
    };
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
