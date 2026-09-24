import { minLod } from "../silk.js";
import { RECORD_VS, RECORD_FS, BEAD_VS, BEAD_FS, QUAD_VS, COPY_FS, BLUR_FS, BACKGROUND_FS } from "./shaders.js";

const HEADER_BYTES = 32;
const RECORD_BYTES = 20;
const BEAD_STRIDE = 32;
const TAPS = 7; // centre + 6 bilinear pairs = 13 samples covering ±12 texels
const REACH = 12;

function hexColor(value, fallback) {
  const match = /^#?([0-9a-f]{6})$/i.exec(String(value || ""));
  const hex = match ? match[1] : fallback;
  return [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
}

// Two or more passes of sigma/√passes reproduce a Gaussian of sigma while each pass stays within ±12 texels at 2.4σ.
export function blurKernel(sigma) {
  const passes = Math.max(2, Math.ceil((sigma * 2.4 / REACH) ** 2));
  const s = sigma / Math.sqrt(passes);
  const g = x => Math.exp(-(x * x) / (2 * s * s));
  const offsets = new Float32Array(TAPS);
  const weights = new Float32Array(TAPS);
  weights[0] = g(0);
  let total = weights[0];
  for (let k = 1; k < TAPS; k++) {
    const a = 2 * k - 1;
    const b = 2 * k;
    const w = g(a) + g(b);
    weights[k] = w;
    offsets[k] = (a * g(a) + b * g(b)) / w;
    total += 2 * w;
  }
  for (let k = 0; k < TAPS; k++) weights[k] /= total;
  return { passes, sigmaPerPass: s, offsets, weights };
}

function lowerBound(array, value, end) {
  let low = 0;
  let high = end;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (array[mid] < value) low = mid + 1;
    else high = mid;
  }
  return low;
}

export class GLRenderer {
  static create(canvas, stage, onRestored) {
    const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: true, preserveDrawingBuffer: false });
    if (!gl) return null;
    return new GLRenderer(canvas, gl, stage, onRestored);
  }

  constructor(canvas, gl, stage, onRestored) {
    this.canvas = canvas;
    this.gl = gl;
    this.stage = stage;
    this.stageConfig = null;
    this.onRestored = onRestored;
    this.glowEnabled = true;
    this.mode = "dusk";
    this.lost = false;
    this.recordsDrawnLastFrame = 0;
    this.beadsDrawnLastFrame = 0;
    this.temporaryRecordsDrawnLastFrame = 0;
    this.glBufferUploadsLastFrame = 0;
    this.glBufferUploadsTotal = 0;
    this.rendererName = this.queryRenderer();
    canvas.addEventListener("webglcontextlost", event => {
      event.preventDefault();
      this.lost = true;
    });
    canvas.addEventListener("webglcontextrestored", () => {
      this.lost = false;
      this.setup();
      this.onRestored?.();
    });
    this.setup();
  }

  queryRenderer() {
    const gl = this.gl;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    return String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
  }

  setup() {
    const gl = this.gl;
    this.recordProgram = this.program(RECORD_VS, RECORD_FS);
    this.beadProgram = this.program(BEAD_VS, BEAD_FS);
    this.copyProgram = this.program(QUAD_VS, COPY_FS);
    this.blurProgram = this.program(QUAD_VS, BLUR_FS);
    this.backgroundProgram = this.program(QUAD_VS, BACKGROUND_FS);
    this.quadVao = gl.createVertexArray();
    this.floatTargets = Boolean(gl.getExtension("EXT_color_buffer_float"));
    this.resources = new WeakMap();
    this.targets = null;
    this.kernelKey = null;
  }

  program(vsSource, fsSource) {
    const gl = this.gl;
    const compile = (type, source) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS) && !gl.isContextLost()) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    };
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vsSource));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fsSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS) && !gl.isContextLost()) throw new Error(gl.getProgramInfoLog(program));
    const uniforms = {};
    const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) || 0;
    for (let i = 0; i < count; i++) {
      const name = gl.getActiveUniform(program, i).name.replace(/\[0\]$/, "");
      uniforms[name] = gl.getUniformLocation(program, name);
    }
    return { program, uniforms };
  }

  setGlow(enabled) {
    this.glowEnabled = Boolean(enabled);
  }

  invalidate() {}

  countUpload() {
    this.glBufferUploadsLastFrame++;
    this.glBufferUploadsTotal++;
  }

  specimenResources(data) {
    let resources = this.resources.get(data);
    if (resources) return resources;
    const gl = this.gl;
    const recordVao = gl.createVertexArray();
    const recordVbo = gl.createBuffer();
    gl.bindVertexArray(recordVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, recordVbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Uint8Array(data.rawBuffer, HEADER_BYTES, data.count * RECORD_BYTES), gl.STATIC_DRAW);
    this.countUpload();
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 4, gl.UNSIGNED_SHORT, false, RECORD_BYTES, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribIPointer(1, 1, gl.UNSIGNED_INT, RECORD_BYTES, 8);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 4, gl.UNSIGNED_BYTE, false, RECORD_BYTES, 12);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, false, RECORD_BYTES, 16);
    for (let i = 0; i < 4; i++) gl.vertexAttribDivisor(i, 1);

    let beadVao = null;
    if (data.beadCount > 0) {
      const bytes = new ArrayBuffer(data.beadCount * BEAD_STRIDE);
      const f32 = new Float32Array(bytes);
      const u32 = new Uint32Array(bytes);
      const u8 = new Uint8Array(bytes);
      for (let b = 0; b < data.beadCount; b++) {
        const host = data.beadHosts[b];
        const o = b * BEAD_STRIDE;
        const s = host * 8;
        f32[o / 4] = data.beadX[b];
        f32[o / 4 + 1] = data.beadY[b];
        f32[o / 4 + 2] = data.beadRadii[b];
        u32[o / 4 + 3] = host;
        u32[o / 4 + 4] = data.deaths[host];
        u8[o + 20] = data.styles[s + 2];
        u8[o + 21] = data.styles[s + 3];
        u8[o + 22] = data.styles[s + 4];
        u8[o + 23] = data.styles[s + 7];
        u8[o + 24] = data.styles[s + 5];
        u8[o + 25] = data.styles[s + 6];
        u8[o + 26] = data.beadFlags[b];
        f32[o / 4 + 7] = data.beadU[b];
      }
      beadVao = gl.createVertexArray();
      const beadVbo = gl.createBuffer();
      gl.bindVertexArray(beadVao);
      gl.bindBuffer(gl.ARRAY_BUFFER, beadVbo);
      gl.bufferData(gl.ARRAY_BUFFER, u8, gl.STATIC_DRAW);
      this.countUpload();
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, BEAD_STRIDE, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribIPointer(1, 2, gl.UNSIGNED_INT, BEAD_STRIDE, 12);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2, 4, gl.UNSIGNED_BYTE, true, BEAD_STRIDE, 20);
      gl.enableVertexAttribArray(3);
      gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, false, BEAD_STRIDE, 24);
      gl.enableVertexAttribArray(4);
      gl.vertexAttribPointer(4, 1, gl.FLOAT, false, BEAD_STRIDE, 28);
      for (let i = 0; i < 5; i++) gl.vertexAttribDivisor(i, 1);
    }
    gl.bindVertexArray(null);
    resources = { recordVao, beadVao };
    this.resources.set(data, resources);
    return resources;
  }

  makeTarget(width, height, float) {
    const gl = this.gl;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (float) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, width, height, 0, gl.RGBA, gl.HALF_FLOAT, null);
    else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this.countUpload();
    const framebuffer = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    return { texture, framebuffer, width, height };
  }

  ensureTargets(width, height) {
    if (this.targets && this.targets.width === width && this.targets.height === height) return this.targets;
    const gl = this.gl;
    if (this.targets) {
      for (const target of [this.targets.sharp, this.targets.a, this.targets.b]) {
        gl.deleteTexture(target.texture);
        gl.deleteFramebuffer(target.framebuffer);
      }
    }
    const halfWidth = Math.max(1, Math.ceil(width / 2));
    const halfHeight = Math.max(1, Math.ceil(height / 2));
    this.targets = {
      width, height,
      sharp: this.makeTarget(width, height, false),
      a: this.makeTarget(halfWidth, halfHeight, this.floatTargets),
      b: this.makeTarget(halfWidth, halfHeight, this.floatTargets),
    };
    return this.targets;
  }

  kernel() {
    const radius = this.stageConfig?.glow?.radius ?? 14;
    const sigma = radius * 0.5 * this.stage.dpr;
    if (this.kernelKey !== sigma) {
      this.kernelData = blurKernel(sigma);
      this.kernelKey = sigma;
    }
    return this.kernelData;
  }

  drawQuad(program, texture, uniforms = {}) {
    const gl = this.gl;
    gl.useProgram(program.program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(program.uniforms.u_tex, 0);
    for (const [name, apply] of Object.entries(uniforms)) apply(program.uniforms[name]);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  render(instances) {
    this.glBufferUploadsLastFrame = 0;
    this.recordsDrawnLastFrame = 0;
    this.beadsDrawnLastFrame = 0;
    this.temporaryRecordsDrawnLastFrame = 0;
    const gl = this.gl;
    if (this.lost || gl.isContextLost()) return;
    const width = this.canvas.width;
    const height = this.canvas.height;
    const dpr = this.stage.dpr;
    const targets = this.ensureTargets(width, height);

    gl.bindFramebuffer(gl.FRAMEBUFFER, targets.sharp.framebuffer);
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    for (const instance of instances) {
      const { data, cursor, placement } = instance;
      if (!data.count) continue;
      const resources = this.specimenResources(data);
      const xform = [placement.originX * dpr, placement.originY * dpr, placement.scale * dpr];
      const threshold = minLod(placement.detail);
      const fadeRecords = instance.specimen.fadeRecords || 6;
      const drawn = Math.min(data.count, Math.ceil(cursor));
      const record = this.recordProgram;
      gl.useProgram(record.program);
      gl.uniform2f(record.uniforms.u_viewport, width, height);
      gl.uniform3f(record.uniforms.u_xform, ...xform);
      gl.uniform1f(record.uniforms.u_scale, placement.scale);
      gl.uniform1f(record.uniforms.u_dpr, dpr);
      gl.uniform1f(record.uniforms.u_minLod, threshold);
      gl.uniform1f(record.uniforms.u_minWidthPx, 0.55);
      gl.uniform1f(record.uniforms.u_coordScale, data.coordScale);
      gl.uniform1f(record.uniforms.u_widthScale, data.widthScale);
      gl.uniform1f(record.uniforms.u_cursor, cursor);
      gl.uniform1f(record.uniforms.u_N, data.count);
      gl.uniform1f(record.uniforms.u_fadeRecords, fadeRecords);
      gl.bindVertexArray(resources.recordVao);
      if (drawn > 0) gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, drawn);
      this.recordsDrawnLastFrame += drawn;
      const beads = resources.beadVao ? lowerBound(data.beadHosts, Math.floor(cursor), data.beadCount) : 0;
      if (beads > 0) {
        const bead = this.beadProgram;
        gl.useProgram(bead.program);
        gl.uniform2f(bead.uniforms.u_viewport, width, height);
        gl.uniform3f(bead.uniforms.u_xform, ...xform);
        gl.uniform1f(bead.uniforms.u_minLod, threshold);
        gl.uniform1f(bead.uniforms.u_dewAge, placement.detail < 0.35 ? -1 : instance.dewAge);
        gl.uniform1f(bead.uniforms.u_cursor, cursor);
        gl.uniform1f(bead.uniforms.u_N, data.count);
        gl.uniform1f(bead.uniforms.u_fadeRecords, fadeRecords);
        gl.bindVertexArray(resources.beadVao);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, beads);
        this.beadsDrawnLastFrame += beads;
      }
    }

    const glow = this.glowEnabled && instances.length > 0;
    if (glow) {
      const { passes, offsets, weights } = this.kernel();
      const { a, b } = targets;
      gl.disable(gl.BLEND);
      gl.viewport(0, 0, a.width, a.height);
      gl.bindFramebuffer(gl.FRAMEBUFFER, a.framebuffer);
      this.drawQuad(this.copyProgram, targets.sharp.texture, { u_gain: l => gl.uniform1f(l, 1) });
      const blur = (source, destination, x, y) => {
        gl.bindFramebuffer(gl.FRAMEBUFFER, destination.framebuffer);
        this.drawQuad(this.blurProgram, source.texture, {
          u_step: l => gl.uniform2f(l, x / a.width, y / a.height),
          u_offsets: l => gl.uniform1fv(l, offsets),
          u_weights: l => gl.uniform1fv(l, weights),
        });
      };
      for (let pass = 0; pass < passes; pass++) {
        blur(a, b, 1, 0);
        blur(b, a, 0, 1);
      }
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, width, height);
    const dusk = hexColor(this.stageConfig?.background, "05060c");
    const dawn = this.mode === "dawn";
    const top = dawn ? hexColor(this.stageConfig?.dawn?.top, "0b1124") : dusk;
    const bottom = dawn ? hexColor(this.stageConfig?.dawn?.bottom, "1d1521") : dusk;
    gl.disable(gl.BLEND);
    this.drawQuad(this.backgroundProgram, null, {
      u_top: l => gl.uniform3f(l, ...top),
      u_bottom: l => gl.uniform3f(l, ...bottom),
    });
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    this.drawQuad(this.copyProgram, targets.sharp.texture, { u_gain: l => gl.uniform1f(l, 1) });
    if (glow) {
      const strength = (this.stageConfig?.glow?.strength ?? 0.5) * (this.mode === "dawn" ? 1.2 : 1);
      gl.blendFunc(gl.ONE, gl.ONE);
      this.drawQuad(this.copyProgram, targets.a.texture, { u_gain: l => gl.uniform1f(l, strength) });
    }
    gl.bindVertexArray(null);
  }
}
