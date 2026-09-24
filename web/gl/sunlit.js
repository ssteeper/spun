// The Sunlit look: a HDR pipeline drawn around the same frozen .silk records as the classic look.
// canopy → backdrop (+bokeh) → light (ray-marched shafts + sun visibility) → scene (leaves, silk,
// dew, spiders, motes) → foreground leaves → bloom and star filter → graded composite.

import { minLod } from "../silk.js";
import {
  FULLSCREEN_VS, FAR_FOLIAGE_FS, LEAF_VS, LEAF_FS, BACKDROP_FS, BOKEH_VS, BOKEH_FS, RAYS_FS, BLUR9_FS, COPY_FS,
  SILK_VS, SILK_FS, LEAFMESH_VS, LEAFMESH_FS, DEW_VS, DEW_FS, MOTE_VS, MOTE_FS, BLOOM_DOWN_FS, BLOOM_UP_FS,
  STREAK_FS, BRIGHT_FS, COMPOSITE_FS,
} from "./sunlitShaders.js";
import { generateCanopy, generateForeground, generateBokeh, generateMotes, hexToRgb, INSTANCE_FLOATS } from "./canopy.js";
import { buildLeafMesh, LEAF_VERTEX_FLOATS } from "./leafMesh.js";
import { SpiderRenderer } from "./spiders.js";

export const QUALITY = Object.freeze({
  low: { canopy: 0.22, rays: 0.25, steps: 28, backdrop: 0.5, bloom: 4, star: false, spiderSteps: 56, spiderShadow: false, motes: 160 },
  medium: { canopy: 0.3, rays: 0.33, steps: 44, backdrop: 0.5, bloom: 5, star: true, spiderSteps: 72, spiderShadow: false, motes: 260 },
  high: { canopy: 0.4, rays: 0.5, steps: 64, backdrop: 0.5, bloom: 6, star: true, spiderSteps: 96, spiderShadow: true, motes: 340 },
  ultra: { canopy: 0.55, rays: 0.5, steps: 96, backdrop: 1, bloom: 7, star: true, spiderSteps: 128, spiderShadow: true, motes: 420 },
});

const EYE_Z = 1.374;          // focal distance in stage heights (a ~40° vertical field of view)
const CANOPY_MARGIN = 0.45;   // h units beyond each stage edge covered by the canopy target
const SUN_SCALE = 3.2;        // sun radiance per unit of the Brightness slider

function linear(hex, scale = 1) {
  return hexToRgb(hex).map(v => Math.pow(v, 2.2) * scale);
}

function normalize3(v) {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}

// White-balance gains from a warmth of -1 (cool) to 1 (warm).
function whiteBalance(warmth) {
  return [1 + 0.18 * warmth, 1 + 0.02 * warmth, 1 - 0.22 * warmth];
}

export class SunlitPipeline {
  constructor(owner) {
    this.owner = owner;
    this.gl = owner.gl;
    this.stats = { canopyInstances: 0, leafMeshes: 0, spidersDrawn: 0, dewDrawn: 0, framesRendered: 0 };
    this.setup();
  }

  static supported(gl) {
    return Boolean(gl.getExtension("EXT_color_buffer_float"));
  }

  setup() {
    const program = (vs, fs) => this.owner.program(vs, fs);
    this.p = {
      far: program(FULLSCREEN_VS, FAR_FOLIAGE_FS),
      leaf: program(LEAF_VS, LEAF_FS),
      backdrop: program(FULLSCREEN_VS, BACKDROP_FS),
      bokeh: program(BOKEH_VS, BOKEH_FS),
      rays: program(FULLSCREEN_VS, RAYS_FS),
      blur: program(FULLSCREEN_VS, BLUR9_FS),
      copy: program(FULLSCREEN_VS, COPY_FS),
      silk: program(SILK_VS, SILK_FS),
      leafMesh: program(LEAFMESH_VS, LEAFMESH_FS),
      dew: program(DEW_VS, DEW_FS),
      mote: program(MOTE_VS, MOTE_FS),
      down: program(FULLSCREEN_VS, BLOOM_DOWN_FS),
      up: program(FULLSCREEN_VS, BLOOM_UP_FS),
      streak: program(FULLSCREEN_VS, STREAK_FS),
      bright: program(FULLSCREEN_VS, BRIGHT_FS),
      composite: program(FULLSCREEN_VS, COMPOSITE_FS),
    };
    this.quadVao = this.gl.createVertexArray();
    this.targets = null;
    this.content = null;
    this.contentKey = "";
    this.leafMeshes = new WeakMap();
    this.spiders = new SpiderRenderer(this.owner, this);
  }

  // ---------------------------------------------------------------- resources

  target(width, height, { float = true, mipmap = false } = {}) {
    const gl = this.gl;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    const w = Math.max(1, Math.round(width));
    const h = Math.max(1, Math.round(height));
    const levels = mipmap ? Math.floor(Math.log2(Math.max(w, h))) + 1 : 1;
    gl.texStorage2D(gl.TEXTURE_2D, levels, float ? gl.RGBA16F : gl.RGBA8, w, h);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mipmap ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.owner.countUpload();
    const framebuffer = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    return { texture, framebuffer, width: w, height: h, mipmap };
  }

  releaseTargets() {
    if (!this.targets) return;
    const gl = this.gl;
    const all = [];
    const collect = value => {
      if (!value || typeof value !== "object") return;
      if (value.texture) all.push(value);
      else Object.values(value).forEach(collect);
    };
    Object.values(this.targets).forEach(collect);
    for (const target of all) {
      gl.deleteTexture(target.texture);
      gl.deleteFramebuffer(target.framebuffer);
    }
    this.targets = null;
  }

  // Soft passes (canopy, light, backdrop) are sized from CSS pixels: they are blurry by nature and
  // gain nothing from a high device-pixel ratio. The scene and bloom follow the canvas.
  ensureTargets(width, height, aspect, quality, dpr) {
    const key = `${width}x${height}|${aspect.toFixed(4)}|${quality.name}|${dpr}`;
    if (this.targets?.key === key) return this.targets;
    this.releaseTargets();
    const soft = 1 / Math.max(1, dpr);
    const canopyH = height * soft * quality.canopy * (1 + 2 * CANOPY_MARGIN);
    const canopyW = height * soft * quality.canopy * (aspect + 2 * CANOPY_MARGIN);
    const bloom = [];
    let bw = width / 2;
    let bh = height / 2;
    for (let level = 0; level < quality.bloom; level++) {
      bloom.push(this.target(bw, bh));
      bw /= 2;
      bh /= 2;
    }
    const quarterW = width / 4;
    const quarterH = height / 4;
    this.targets = {
      key,
      canopy: this.target(canopyW, canopyH, { mipmap: true }),
      backdrop: this.target(width * soft * quality.backdrop, height * soft * quality.backdrop, { mipmap: true }),
      light: this.target(width * soft * quality.rays, height * soft * quality.rays, { float: false }),
      lightTmp: this.target(width * soft * quality.rays, height * soft * quality.rays, { float: false }),
      scene: this.target(width, height),
      foreground: this.target(quarterW, quarterH),
      bloom,
      star: { sum: this.target(quarterW, quarterH), a: this.target(quarterW, quarterH), b: this.target(quarterW, quarterH), bright: this.target(quarterW, quarterH) },
      canopyTexelH: 1 / (height * soft * quality.canopy),
    };
    return this.targets;
  }

  instanceVao(data, layout) {
    const gl = this.gl;
    const vao = gl.createVertexArray();
    const vbo = gl.createBuffer();
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    this.owner.countUpload();
    const stride = layout.reduce((sum, size) => sum + size, 0) * 4;
    let offset = 0;
    layout.forEach((size, location) => {
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, stride, offset);
      gl.vertexAttribDivisor(location, 1);
      offset += size * 4;
    });
    gl.bindVertexArray(null);
    return { vao, vbo };
  }

  ensureContent(settings) {
    const f = settings.values.foliage;
    const key = `${f.seed}|${f.density}|${f.leafSize}|${f.leafColor}|${f.foreground}`;
    if (this.content && this.contentKey === key) return this.content;
    const gl = this.gl;
    if (this.content) {
      for (const part of Object.values(this.content)) {
        if (part?.vao) {
          gl.deleteVertexArray(part.vao);
          gl.deleteBuffer(part.vbo);
        }
      }
    }
    const canopy = generateCanopy({ seed: f.seed, density: f.density, leafSize: f.leafSize, leafColor: f.leafColor });
    const foreground = generateForeground({ seed: f.seed, amount: f.foreground, leafSize: f.leafSize, leafColor: f.leafColor });
    const bokeh = generateBokeh({ seed: f.seed });
    const motes = generateMotes({ seed: f.seed });
    const vec4x4 = [4, 4, 4, 4];
    this.content = {
      canopy: canopy.count ? { ...this.instanceVao(canopy.data, vec4x4), count: canopy.count } : null,
      foreground: foreground.count ? { ...this.instanceVao(foreground.data, vec4x4), count: foreground.count } : null,
      bokeh: { ...this.instanceVao(bokeh.data, [4, 4]), count: bokeh.count },
      motes: { ...this.instanceVao(motes.data, [4, 4]), count: motes.count },
    };
    this.contentKey = key;
    this.stats.canopyInstances = canopy.count;
    return this.content;
  }

  leafMesh(data) {
    let mesh = this.leafMeshes.get(data);
    if (mesh) return mesh;
    const gl = this.gl;
    const built = buildLeafMesh(data);
    mesh = { count: built.count, shapes: built.shapes, vao: null };
    if (built.count) {
      mesh.vao = gl.createVertexArray();
      const vbo = gl.createBuffer();
      gl.bindVertexArray(mesh.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
      gl.bufferData(gl.ARRAY_BUFFER, built.data, gl.STATIC_DRAW);
      this.owner.countUpload();
      const stride = LEAF_VERTEX_FLOATS * 4;
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 4, gl.FLOAT, false, stride, 8);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2, 4, gl.FLOAT, false, stride, 24);
      gl.bindVertexArray(null);
    }
    this.leafMeshes.set(data, mesh);
    return mesh;
  }

  // ---------------------------------------------------------------- helpers

  use(program, values = {}) {
    const gl = this.gl;
    gl.useProgram(program.program);
    let unit = 0;
    for (const [name, value] of Object.entries(values)) {
      const location = program.uniforms[name];
      if (location == null) continue;
      if (value && value.texture !== undefined) {
        gl.activeTexture(gl.TEXTURE0 + unit);
        gl.bindTexture(gl.TEXTURE_2D, value.texture);
        gl.uniform1i(location, unit++);
      } else if (value instanceof Int32Array) {
        gl.uniform1i(location, value[0]);
      } else if (typeof value === "number") {
        gl.uniform1f(location, value);
      } else if (value.length === 2) {
        gl.uniform2fv(location, value);
      } else if (value.length === 3) {
        gl.uniform3fv(location, value);
      } else if (value.length === 4) {
        gl.uniform4fv(location, value);
      }
    }
  }

  bind(target) {
    const gl = this.gl;
    if (target) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.framebuffer);
      gl.viewport(0, 0, target.width, target.height);
    } else {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.gl.canvas.width, this.gl.canvas.height);
    }
  }

  fullscreen(program, values) {
    this.use(program, values);
    this.gl.bindVertexArray(this.quadVao);
    this.gl.drawArrays(this.gl.TRIANGLE_STRIP, 0, 4);
  }

  blend(mode) {
    const gl = this.gl;
    if (mode === "none") {
      gl.disable(gl.BLEND);
      return;
    }
    gl.enable(gl.BLEND);
    if (mode === "add") gl.blendFunc(gl.ONE, gl.ONE);
    else gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }

  // ---------------------------------------------------------------- lighting

  environment(frame) {
    const { settings, mode, stage } = frame;
    const s = settings.values;
    const light = s.light[mode];
    const aspect = stage.width / stage.height;
    const sunH = [(light.sunX - 0.5) * aspect, light.sunY];
    const toSun = normalize3([sunH[0], sunH[1] - 0.5, -EYE_Z]);
    const b = light.backlight;
    const sunDir = normalize3([toSun[0], toSun[1], toSun[2] * (2 * b - 1) - (b === 0.5 ? 0.001 : 0)]);
    const skyTop = linear(light.skyTop);
    const skyHorizon = linear(light.skyHorizon);
    const hazeColor = linear(light.hazeColor);
    // Fill light takes its hue from the open sky above and the mist, so shade reads cool
    // against a warm sun; its strength is the Sky fill slider.
    const hue = c => {
      const y = Math.max(1e-3, 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]);
      return c.map(v => v / y);
    };
    const top = hue(skyTop);
    const mist = hue(hazeColor);
    const fill = top.map((v, i) => 0.7 * (0.6 * v + 0.4 * mist[i]) + 0.3);
    return {
      aspect,
      sunH,
      sunDir,
      backlight: b,
      sunRadiance: linear(light.sunColor, light.intensity * SUN_SCALE),
      sunSize: light.sunSize,
      skyTop,
      skyHorizon,
      hazeColor,
      haze: light.haze,
      rays: light.rays,
      rayLength: light.rayLength,
      ambient: fill.map(v => v * 0.1 * (0.25 + 3 * light.ambient)),
      motes: light.motes,
      foliage: linear(s.foliage.leafColor),
      ground: linear(s.foliage.leafColor).map((v, i) => (0.55 * v + 0.45 * [0.05, 0.09, 0.08][i]) * fill[i] * 0.1 * (0.25 + 3 * light.ambient) * 0.45),
      eye: [stage.width / 2, stage.height / 2, EYE_Z * stage.height],
    };
  }

  // ---------------------------------------------------------------- frame

  render(instances, frame) {
    const gl = this.gl;
    const { settings, stage, time, quality } = frame;
    const s = settings.values;
    const width = gl.canvas.width;
    const height = gl.canvas.height;
    const dpr = stage.dpr;
    const env = this.environment(frame);
    const targets = this.ensureTargets(width, height, env.aspect, quality, dpr);
    const content = this.ensureContent(settings);
    const motion = frame.motion;
    const stageSize = [stage.width, stage.height];
    const canopyMin = [-env.aspect / 2 - CANOPY_MARGIN, -CANOPY_MARGIN];
    const canopySize = [env.aspect + 2 * CANOPY_MARGIN, 1 + 2 * CANOPY_MARGIN];
    const space = { u_stage: stageSize, u_canopyMin: canopyMin, u_canopySize: canopySize };
    const blurSetting = s.foliage.blur;
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);

    // 1. Canopy: distant bush, then branches and leaves far to near; mipmapped for cone tracing.
    this.bind(targets.canopy);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    this.blend("over");
    const lightUniforms = {
      u_sunRadiance: env.sunRadiance, u_ambient: env.ambient, u_hazeColor: env.hazeColor,
      u_haze: env.haze, u_backlight: env.backlight,
    };
    this.fullscreen(this.p.far, {
      ...space, ...lightUniforms, u_density: s.foliage.density, u_seed: (s.foliage.seed % 1000) / 1000,
      u_time: time, u_motion: motion, u_foliage: env.foliage, u_sunH: env.sunH,
    });
    if (content.canopy) {
      this.use(this.p.leaf, {
        ...lightUniforms, u_regionMin: canopyMin, u_regionSize: canopySize, u_fractions: 0, u_aspect: env.aspect,
        u_time: time, u_motion: motion, u_blurMin: 0.002 + 0.014 * blurSetting, u_blurMax: 0.005 + 0.06 * blurSetting,
        u_texel: targets.canopyTexelH, u_veil: 1, u_rim: 1, u_brightness: 1,
      });
      gl.bindVertexArray(content.canopy.vao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, content.canopy.count);
    }
    gl.bindTexture(gl.TEXTURE_2D, targets.canopy.texture);
    gl.generateMipmap(gl.TEXTURE_2D);

    // 2. Backdrop: sky, sun and canopy; bokeh added on top.
    this.bind(targets.backdrop);
    this.blend("none");
    this.fullscreen(this.p.backdrop, {
      ...space, u_canopy: targets.canopy, u_sunH: env.sunH, u_sunRadiance: env.sunRadiance, u_skyTop: env.skyTop,
      u_skyHorizon: env.skyHorizon, u_hazeColor: env.hazeColor, u_haze: env.haze, u_backlight: env.backlight, u_sunSize: env.sunSize,
      u_ground: env.ground,
    });
    if (s.foliage.bokeh > 0) {
      this.blend("add");
      this.use(this.p.bokeh, {
        ...space, u_canopy: targets.canopy, u_sunH: env.sunH, u_sunRadiance: env.sunRadiance, u_hazeColor: env.hazeColor,
        u_backlight: env.backlight, u_amount: s.foliage.bokeh, u_size: s.foliage.bokehSize, u_time: time, u_motion: motion,
        u_blades: s.foliage.blades, u_pxPerH: targets.backdrop.height,
      });
      gl.bindVertexArray(content.bokeh.vao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, content.bokeh.count);
    }
    gl.bindTexture(gl.TEXTURE_2D, targets.backdrop.texture);
    gl.generateMipmap(gl.TEXTURE_2D);

    // 3. Light: ray-marched shafts and sun visibility, lightly blurred to hide the jitter.
    this.bind(targets.light);
    this.blend("none");
    this.fullscreen(this.p.rays, {
      ...space, u_canopy: targets.canopy, u_sunH: env.sunH, u_rayLen: 0.25 + 1.6 * env.rayLength,
      u_steps: new Int32Array([quality.steps]), u_webDist: 0.42, u_penumbra: 0.04 * env.sunSize,
      u_texelH: targets.canopyTexelH, u_jitter: motion > 0 ? (time * 0.618) % 1 : 0,
    });
    this.bind(targets.lightTmp);
    this.fullscreen(this.p.blur, { u_tex: targets.light, u_step: [1 / targets.light.width, 0] });
    this.bind(targets.light);
    this.fullscreen(this.p.blur, { u_tex: targets.lightTmp, u_step: [0, 1 / targets.light.height] });

    // 4. Scene at full resolution.
    this.bind(targets.scene);
    this.blend("none");
    this.fullscreen(this.p.copy, { u_tex: targets.backdrop });
    this.blend("over");
    const view = frame.view;
    const shading = {
      u_light: targets.light, u_sunDir: env.sunDir, u_sunRadiance: env.sunRadiance, u_ambient: env.ambient,
      u_eye: env.eye, u_viewport: [width, height], u_dpr: dpr, u_view: [view.zoom, view.tx, view.ty],
    };
    const leafTint = linear(s.foliage.leafColor);
    this.stats.dewDrawn = 0;
    for (const instance of instances) this.drawInstance(instance, frame, env, shading, leafTint);
    this.stats.spidersDrawn = this.spiders.draw(instances, frame, env, shading);
    if (env.motes > 0) {
      this.blend("add");
      this.use(this.p.mote, {
        u_light: targets.light, u_stage: stageSize, u_dpr: dpr, u_time: time, u_motion: motion,
        u_amount: env.motes * env.haze * 1.4 + env.motes * 0.2, u_sunRadiance: env.sunRadiance,
      });
      gl.bindVertexArray(content.motes.vao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, Math.min(content.motes.count, quality.motes));
    }

    // 5. Foreground leaves near the lens, heavily defocused.
    const foreground = Boolean(content.foreground) && s.foliage.foreground > 0;
    if (foreground) {
      this.bind(targets.foreground);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      this.blend("over");
      this.use(this.p.leaf, {
        ...lightUniforms, u_regionMin: [-env.aspect / 2, 0], u_regionSize: [env.aspect, 1], u_fractions: 1, u_aspect: env.aspect,
        u_time: time, u_motion: motion, u_blurMin: 0.045 + 0.05 * blurSetting, u_blurMax: 0.045 + 0.05 * blurSetting,
        u_texel: 4 / height, u_veil: 0, u_rim: 0, u_brightness: 0.8,
      });
      gl.bindVertexArray(content.foreground.vao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, content.foreground.count);
    }

    // 6. Bloom chain, with star streaks taken from the quarter-resolution level.
    this.blend("none");
    let source = targets.scene;
    targets.bloom.forEach((level, index) => {
      this.bind(level);
      this.fullscreen(this.p.down, {
        u_tex: source, u_texel: [1 / source.width, 1 / source.height], u_prefilter: index === 0 ? 1 : 0,
        u_threshold: 1.0, u_knee: 0.6,
      });
      source = level;
    });
    const starPoints = Number(s.dew.star) || 0;
    const starOn = quality.star && starPoints > 0;
    if (starOn) this.drawStar(targets, starPoints);
    this.blend("add");
    for (let index = targets.bloom.length - 1; index > 0; index--) {
      const from = targets.bloom[index];
      this.bind(targets.bloom[index - 1]);
      this.fullscreen(this.p.up, { u_tex: from, u_texel: [1 / from.width, 1 / from.height], u_radius: 1, u_weight: 0.85 });
    }

    // 7. Composite and grade into the canvas.
    this.bind(null);
    this.blend("none");
    const cam = s.camera;
    this.fullscreen(this.p.composite, {
      ...space, u_scene: targets.scene, u_bloomTex: targets.bloom[0], u_starTex: targets.star.sum,
      u_light: targets.light, u_foreground: targets.foreground, u_canopy: targets.canopy, u_sunH: env.sunH,
      u_sunRadiance: env.sunRadiance, u_hazeColor: env.hazeColor, u_sunDir: env.sunDir, u_haze: env.haze, u_rays: env.rays,
      u_backlight: env.backlight, u_bloom: cam.bloom, u_star: starOn ? 0.55 * s.dew.glint : 0, u_exposure: cam.exposure,
      u_contrast: cam.contrast, u_saturation: cam.saturation, u_whiteBalance: whiteBalance(cam.warmth), u_vignette: cam.vignette,
      u_grain: cam.grain, u_aberration: cam.aberration, u_flare: cam.flare, u_time: motion > 0 ? time : 0,
      u_foregroundOn: foreground ? 1 : 0, u_eyeZ: EYE_Z, u_debug: this.debugView || 0,
      u_spikes: s.foliage.blades % 2 ? s.foliage.blades * 2 : s.foliage.blades, u_sunSize: env.sunSize,
    });
    gl.bindVertexArray(null);
    this.stats.framesRendered++;
  }

  drawStar(targets, points) {
    const gl = this.gl;
    const { sum, a, b, bright } = targets.star;
    this.blend("none");
    this.bind(bright);
    this.fullscreen(this.p.bright, { u_tex: targets.scene, u_texel: [1 / targets.scene.width, 1 / targets.scene.height] });
    const source = bright;
    this.bind(sum);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const lines = points / 2;
    const texel = [1 / a.width, 1 / a.height];
    for (let line = 0; line < lines; line++) {
      const angle = Math.PI / 4 + (line * Math.PI) / lines;
      const dir = [Math.cos(angle) * texel[0], Math.sin(angle) * texel[1]];
      this.blend("none");
      this.bind(a);
      this.fullscreen(this.p.streak, { u_tex: source, u_dir: dir, u_pass: 0, u_threshold: 7.0 });
      this.bind(b);
      this.fullscreen(this.p.streak, { u_tex: a, u_dir: dir, u_pass: 1, u_threshold: 0 });
      this.bind(a);
      this.fullscreen(this.p.streak, { u_tex: b, u_dir: dir, u_pass: 2, u_threshold: 0 });
      this.blend("add");
      this.bind(sum);
      this.fullscreen(this.p.copy, { u_tex: a });
    }
    this.blend("none");
  }

  drawInstance(instance, frame, env, shading, leafTint) {
    const gl = this.gl;
    const { data, cursor, placement } = instance;
    if (!data.count) return;
    const s = frame.settings.values;
    const dpr = frame.stage.dpr;
    const resources = this.owner.specimenResources(data);
    const { zoom, tx, ty } = frame.view;
    const scale = placement.scale * zoom;
    const xform = [(placement.originX * zoom + tx) * dpr, (placement.originY * zoom + ty) * dpr, scale * dpr];
    const threshold = minLod(Math.min(1, placement.detail * zoom));
    const fadeRecords = instance.specimen.fadeRecords || 6;
    const drawn = Math.min(data.count, Math.ceil(cursor));
    const mesh = this.leafMesh(data);
    if (mesh.vao) {
      this.use(this.p.leafMesh, { ...shading, u_xform: xform, u_cursor: cursor, u_leafTint: leafTint });
      gl.bindVertexArray(mesh.vao);
      gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
    }
    if (drawn > 0) {
      this.use(this.p.silk, {
        ...shading, u_xform: xform, u_scale: scale, u_minLod: threshold, u_minWidthPx: 0.55,
        u_coordScale: data.coordScale, u_widthScale: data.widthScale, u_thickness: s.silk.thickness, u_cursor: cursor,
        u_silkZoom: Math.pow(zoom, -0.7),
        u_N: data.count, u_fadeRecords: fadeRecords, u_brightness: s.silk.brightness, u_iridescence: s.silk.iridescence,
        u_sheen: s.silk.sheen, u_sparkle: s.silk.sparkle, u_leafTint: leafTint,
      });
      gl.bindVertexArray(resources.recordVao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, drawn);
    }
    const beads = resources.beadVao ? this.owner.beadsBefore(data, cursor) : 0;
    if (beads > 0) {
      this.use(this.p.dew, {
        ...shading, u_xform: xform, u_minLod: threshold, u_dewAge: placement.detail * zoom < 0.35 ? -1 : instance.dewAge,
        u_cursor: cursor, u_N: data.count, u_fadeRecords: fadeRecords, u_amount: s.dew.amount, u_size: s.dew.size,
        u_backdrop: this.targets.backdrop, u_refraction: s.dew.refraction, u_glint: s.dew.glint,
        u_lensDist: 0.3 * gl.canvas.height, u_skyTop: env.skyTop, u_skyHorizon: env.skyHorizon,
      });
      gl.bindVertexArray(resources.beadVao);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, beads);
      this.stats.dewDrawn += beads;
    }
  }
}
