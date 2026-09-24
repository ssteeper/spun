// Ray-marched 3-D spiders for the Sunlit look: one screen quad per spider, posed each frame from
// the same gait and rest data as the glyph overlay. Only uniforms change, so no buffers upload.

import { activeSpiders, blendedLegs } from "../core/spiderPose.js";
import { speciesUniforms, liftLeg, PATTERN } from "./spiderModels.js";
import { SPIDER_VS, SPIDER_FS } from "./spiderShaders.js";

function hexColor(value, fallback) {
  const text = typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
  const n = parseInt(text.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255].map(v => Math.pow(v, 2.2));
}

// Which glyph extras hold each species' pattern colours (see spun/spider.py _body()).
function patternColours(species, glyph) {
  const body = glyph.body || [];
  const fill = (index, fallback) => hexColor(body[index]?.fill, fallback);
  const accent = species.colAccent;
  switch (species.pattern) {
    case PATTERN.golden: return [fill(3, "#d8bd70"), fill(6, "#5b584e"), accent];
    case PATTERN.argiope: return [fill(3, "#24252a"), fill(6, "#f1dd72"), accent];
    case PATTERN.garden: return [fill(3, "#a78a63"), fill(5, "#b19b7b"), accent];
    case PATTERN.leafCurler: return [fill(3, "#634e35"), accent, accent];
    case PATTERN.jewel: return [fill(9, "#f2ebd5"), fill(13, "#f2d254"), hexColor("#ddd4ad", "#ddd4ad")];
    case PATTERN.scorpionTail: return [fill(3, "#b5904e"), fill(4, "#ddbd78"), accent];
    case PATTERN.netCaster: return [fill(3, "#45392f"), fill(4, "#a48966"), accent];
    case PATTERN.magnificent: return [fill(3, "#dc9da4"), fill(4, "#eac46b"), fill(9, "#f4d9bc")];
    case PATTERN.redback: return [fill(4, "#cf3440"), fill(3, "#42404b"), accent];
    default: return [accent, accent, accent];
  }
}

const HOLDS_SILK = new Set(["net-casting-spider", "magnificent-spider"]);

export class SpiderRenderer {
  constructor(owner) {
    this.owner = owner;
    this.gl = owner.gl;
    this.program = owner.program(SPIDER_VS, SPIDER_FS);
    this.vao = this.gl.createVertexArray();
    this.species = new Map();
    this.joints = new Float32Array(56 * 3);
    this.bounds = new Float32Array(8 * 4);
    this.quad = new Float32Array(8);
  }

  speciesFor(id, glyph) {
    let entry = this.species.get(id);
    if (!entry) {
      entry = speciesUniforms(id, glyph);
      [entry.c1, entry.c2, entry.c3] = patternColours(entry, glyph);
      this.species.set(id, entry);
    }
    return entry;
  }

  // Swing legs lift their tips (alternating tetrapods, as the glyph gait is authored).
  static swingLift(index, gaitPhase) {
    const stanceFirst = ((index % 4) + Math.floor(index / 4)) % 2 === 0;
    const phase = (gaitPhase + (stanceFirst ? 0 : 4)) % 8;
    return phase >= 4 ? Math.sin(Math.PI * (phase - 4) / 4) : 0;
  }

  draw(instances, frame, env, shading) {
    const s = frame.settings.values;
    if (s.spiders.model !== "3d") return 0;
    const gl = this.gl;
    const program = this.program;
    const u = program.uniforms;
    const dpr = frame.stage.dpr;
    const size = s.spiders.size;
    const { zoom, tx, ty } = frame.view;
    let drawn = 0;
    gl.useProgram(program.program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, shading.u_light.texture);
    gl.uniform1i(u.u_light, 0);
    gl.uniform2f(u.u_viewport, gl.canvas.width, gl.canvas.height);
    gl.uniform1f(u.u_dpr, dpr);
    gl.uniform3f(u.u_view, zoom, tx, ty);
    gl.uniform3fv(u.u_sunDir, env.sunDir);
    gl.uniform3fv(u.u_sunRadiance, env.sunRadiance);
    gl.uniform3fv(u.u_ambient, env.ambient);
    gl.uniform1i(u.u_steps, frame.quality.spiderSteps);
    gl.uniform1f(u.u_shadows, frame.quality.spiderShadow ? 1 : 0);
    gl.bindVertexArray(this.vao);
    let index = 0;
    for (const { instance, spider, fade, settling, pose } of activeSpiders(instances)) {
      const species = this.speciesFor(instance.specimen.id, spider.glyph);
      const legs = blendedLegs(pose, settling);
      const moving = !(pose.isRest && settling >= 1);
      const L = species.L;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      let zTop = species.bodyZ[0] + species.abd[3];
      // Glyph joint j is point 2j of the seven-point 3-D leg.
      const hideInner = pose.isRest && settling > 0.5 ? Math.max(0, Math.min(3, pose.restVisible.legFromJoint | 0)) : 0;
      const legFrom = 2 * hideInner;
      const bodyVisible = pose.isRest && settling > 0.5 && !pose.restVisible.body ? 0 : 1;
      legs.forEach((leg, legIndex) => {
        const lift = moving ? SpiderRenderer.swingLift(legIndex, pose.gaitPhase) * (1 - settling) : 0;
        const points = liftLeg(leg, species, lift);
        let cx = 0;
        let cy = 0;
        let cz = 0;
        points.forEach((point, k) => {
          this.joints.set(point, (legIndex * 7 + k) * 3);
          cx += point[0] / 7;
          cy += point[1] / 7;
          cz += point[2] / 7;
          if (k >= legFrom) {
            minX = Math.min(minX, point[0]);
            maxX = Math.max(maxX, point[0]);
            minY = Math.min(minY, point[1]);
            maxY = Math.max(maxY, point[1]);
          }
          zTop = Math.max(zTop, point[2]);
        });
        let radius = 0;
        for (const point of points) radius = Math.max(radius, Math.hypot(point[0] - cx, point[1] - cy, point[2] - cz));
        this.bounds.set([cx, cy, cz, radius + species.legR[0] * 1.5], legIndex * 4);
      });
      if (bodyVisible) {
        const [ax, arx, ary] = species.abd;
        const [kx, krx, kry] = species.car;
        const bodyMin = ax - arx * 1.1 - (species.pattern === PATTERN.scorpionTail ? 0.75 * L : 0);
        const bodyMax = kx + krx + 0.3 * L;
        const half = Math.max(ary, kry) * 1.1 + (species.pattern === PATTERN.jewel ? 0.45 * L : 0.05 * L) +
          (species.pattern === PATTERN.scorpionTail ? 0.25 * L : 0);
        const bodyTop = species.bodyZ[0] + species.abd[3] * 1.2 + (species.pattern === PATTERN.magnificent ? 0.25 * L : 0) +
          (species.pattern === PATTERN.scorpionTail ? 0.6 * L : 0) + (species.pattern === PATTERN.jewel ? 0.2 * L : 0);
        minX = Math.min(minX, bodyMin);
        maxX = Math.max(maxX, bodyMax);
        minY = Math.min(minY, -half);
        maxY = Math.max(maxY, half);
        zTop = Math.max(zTop, bodyTop);
        this.bodyBox = [bodyMin, bodyMax, half, bodyTop];
      } else {
        this.bodyBox = [0, 0, 0, 0];
      }
      const margin = species.legR[0] * 2 + 0.03 * L;
      minX -= margin;
      minY -= margin;
      maxX += margin;
      maxY += margin;
      // Spiders whose legs hold silk (the net, the bolas line) keep their true size.
      const held = HOLDS_SILK.has(instance.specimen.id);
      const pxPerMm = pose.scale * dpr * (held ? 1 : size) * zoom;
      const cos = Math.cos(pose.angle);
      const sin = Math.sin(pose.angle);
      const cx = (pose.x * zoom + tx) * dpr;
      const cy = (pose.y * zoom + ty) * dpr;
      const corner = (lx, ly, slot) => {
        this.quad[slot * 2] = cx + (cos * lx - sin * ly) * pxPerMm;
        this.quad[slot * 2 + 1] = cy + (sin * lx + cos * ly) * pxPerMm;
      };
      corner(minX, minY, 0);
      corner(maxX, minY, 1);
      corner(minX, maxY, 2);
      corner(maxX, maxY, 3);
      gl.uniform2fv(u["u_quad"], this.quad);
      gl.uniform2f(u.u_center, cx, cy);
      gl.uniform2f(u.u_axis, cos, sin);
      gl.uniform1f(u.u_pxPerMm, pxPerMm);
      gl.uniform1f(u.u_zTop, zTop + species.legR[0] * 2);
      gl.uniform3fv(u["u_joints"], this.joints);
      gl.uniform4fv(u["u_legBounds"], this.bounds);
      gl.uniform4fv(u.u_bodyBox, this.bodyBox);
      gl.uniform4fv(u.u_abd, species.abd);
      gl.uniform4fv(u.u_car, species.car);
      gl.uniform2fv(u.u_bodyZ, species.bodyZ);
      gl.uniform1f(u.u_L, L);
      gl.uniform3fv(u.u_legR, species.legR);
      gl.uniform1i(u.u_pattern, species.pattern);
      gl.uniform1i(u.u_eyes, species.eyes);
      gl.uniform1i(u.u_bandStyle, species.bandStyle);
      gl.uniform3fv(u.u_colAbd, species.colAbd);
      gl.uniform3fv(u.u_colCar, species.colCar);
      gl.uniform3fv(u.u_colLeg, species.colLeg);
      gl.uniform3fv(u.u_colBand, species.colBand);
      gl.uniform3fv(u.u_c1, species.c1);
      gl.uniform3fv(u.u_c2, species.c2);
      gl.uniform3fv(u.u_c3, species.c3);
      gl.uniform3fv(u.u_colTips, species.colTips);
      gl.uniform3fv(u.u_colTissue, species.colTissue);
      gl.uniform1f(u.u_translucency, species.translucency);
      gl.uniform1f(u.u_bodyVisible, bodyVisible);
      gl.uniform1f(u.u_legFrom, legFrom);
      gl.uniform1f(u.u_breath, frame.motion > 0 ? Math.sin(frame.time * 1.7 + index * 2.1) * frame.motion : 0);
      gl.uniform1f(u.u_fade, fade);
      gl.uniform1f(u.u_gloss, species.gloss * (0.25 + 1.5 * s.spiders.gloss));
      gl.uniform1f(u.u_hair, species.hair * 1.6 * s.spiders.hair);
      gl.uniform1f(u.u_seed, index * 7.31);
      // Spines only when a tibia is several device pixels wide.
      gl.uniform1f(u.u_spines, species.legR[1] * pxPerMm > 2.2 ? 1 : 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      drawn++;
      index++;
    }
    return drawn;
  }
}
