// GLSL ES 3.00 for the Sunlit look. World frame: x right, y down (stage px), z toward the viewer.
// "h-space" is stage px relative to the top-centre, divided by the stage height.

const COMMON = `
precision highp float;
precision highp int;
const float PI = 3.14159265359;
float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
float hash11(float p) {
  p = fract(p * 0.1031);
  p *= p + 33.33;
  p *= p + p;
  return fract(p);
}
float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1.0, 0.0)), u.x), mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float s = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    s += a * vnoise(p);
    p = p * 2.03 + vec2(1.7, 9.2);
    a *= 0.5;
  }
  return s;
}
vec3 toLinear(vec3 c) { return pow(max(c, vec3(0.0)), vec3(2.2)); }
float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
`;

// Stage mapping shared by passes that work in h-space.
const SPACE = `
uniform vec2 u_stage;       // CSS px
uniform vec2 u_canopyMin;   // h-space rectangle covered by the canopy target
uniform vec2 u_canopySize;
vec2 hFromSuv(vec2 suv) { return vec2((suv.x - 0.5) * u_stage.x / u_stage.y, suv.y); }
vec2 suvFromH(vec2 h) { return vec2(h.x * u_stage.y / u_stage.x + 0.5, h.y); }
vec2 canopyTex(vec2 h) { vec2 c = (h - u_canopyMin) / u_canopySize; return vec2(c.x, 1.0 - c.y); }
`;

export const FULLSCREEN_VS = `#version 300 es
out vec2 v_uv;
void main() {
  vec2 p = vec2((gl_VertexID & 1) == 0 ? -1.0 : 1.0, gl_VertexID < 2 ? -1.0 : 1.0);
  v_uv = p * 0.5 + 0.5;
  gl_Position = vec4(p, 0.0, 1.0);
}
`;

// Distant, defocused bush: soft fbm masses that also shade the light shafts.
export const FAR_FOLIAGE_FS = `#version 300 es
${COMMON}
${SPACE}
uniform float u_density;
uniform float u_seed;
uniform float u_time;
uniform float u_motion;
uniform vec3 u_foliage;     // linear
uniform vec3 u_ambient;
uniform vec3 u_hazeColor;
uniform float u_haze;
uniform vec3 u_sunRadiance;
uniform vec2 u_sunH;
uniform float u_backlight;
in vec2 v_uv;
out vec4 o;
void main() {
  vec2 c = vec2(v_uv.x, 1.0 - v_uv.y);
  vec2 h = u_canopyMin + c * u_canopySize;
  vec2 drift = vec2(u_time * 0.004, 0.0) * u_motion;
  float lower = smoothstep(0.1, 1.1, h.y);
  float nearSun = exp(-length(h - u_sunH) / 0.6);
  vec3 shade = mix(u_foliage, vec3(0.05, 0.1, 0.09), 0.3);
  vec3 glow = u_foliage * vec3(1.3, 1.5, 0.6) + vec3(0.02, 0.03, 0.0);
  // Farther layer: paler with distance, lit through where it faces the sun.
  float n1 = fbm(h * vec2(1.3, 1.7) + vec2(u_seed * 17.0, u_seed * 5.0) + drift * 0.6);
  float t1 = mix(0.64, 0.36, u_density) - 0.2 * lower;
  float m1 = smoothstep(t1, t1 + 0.14, n1) * (0.6 + 0.4 * u_density);
  float rim1 = smoothstep(t1 + 0.2, t1 + 0.02, n1);
  float mottle1 = vnoise(h * 11.0 + u_seed * 13.0);
  vec3 c1 = shade * u_ambient * (0.9 + 0.5 * mottle1) + glow * u_sunRadiance * u_backlight * (0.03 + rim1 * nearSun * 0.22);
  c1 = mix(c1, u_hazeColor * (0.05 + 0.3 * nearSun) * max(u_backlight, 0.3), 0.08 + 0.45 * u_haze);
  // Nearer layer: darker clumps with lit edges and mottled leaf texture.
  float n2 = fbm(h * vec2(2.4, 2.9) + vec2(u_seed * 3.0, 11.0) - drift);
  float t2 = mix(0.74, 0.46, u_density) - 0.24 * lower;
  float m2 = smoothstep(t2, t2 + 0.08, n2) * (0.55 + 0.45 * u_density);
  float rim2 = smoothstep(t2 + 0.12, t2 + 0.01, n2);
  float mottle = vnoise(h * 26.0 + u_seed * 40.0) * 0.6 + vnoise(h * 61.0) * 0.4;
  vec3 c2 = shade * u_ambient * (0.35 + 0.4 * mottle) + glow * u_sunRadiance * u_backlight * (0.01 + rim2 * rim2 * nearSun * 0.3);
  c2 = mix(c2, u_hazeColor * (0.03 + 0.2 * nearSun) * max(u_backlight, 0.3), 0.04 + 0.25 * u_haze);
  vec4 far = vec4(c1 * m1, m1 * 0.8);
  vec4 near = vec4(c2 * m2, m2 * 0.7);
  vec4 col = near + far * (1.0 - near.a);
  if (col.a < 0.004) discard;
  o = col;
}
`;

// Instanced canopy leaves and branch capsules. Leaves are analytic lanceolate SDFs whose
// edge width equals the depth-of-field blur, so the backdrop is defocused without blur passes.
export const LEAF_VS = `#version 300 es
${COMMON}
layout(location = 0) in vec4 a0; // x, y, angle, length
layout(location = 1) in vec4 a1; // width, bend, depth, kind
layout(location = 2) in vec4 a2; // r, g, b, phase
layout(location = 3) in vec4 a3; // widthEnd, sway, lit, variant
uniform vec2 u_regionMin;
uniform vec2 u_regionSize;
uniform float u_fractions;   // 1: instance x,y are stage fractions (foreground leaves)
uniform float u_aspect;      // stage width / height
uniform float u_time;
uniform float u_motion;
uniform float u_blurMin;
uniform float u_blurMax;
uniform float u_texel;       // h units per target texel
out vec2 v_local;
flat out vec4 v_shape;       // length, width, bend, kind
flat out vec4 v_color;       // rgb, lit
flat out vec3 v_misc;        // blur, depth, widthEnd
vec2 wind(vec2 p, float depth) {
  float t = u_time;
  vec2 g = vec2(sin(t * 0.71 + p.y * 3.1 + p.x * 1.3) + 0.5 * sin(t * 1.63 + p.x * 4.0 + 1.1),
                0.35 * sin(t * 1.21 + p.x * 2.7) + 0.2 * sin(t * 2.3 + p.y * 5.0));
  return g * 0.0065 * u_motion * (1.15 - 0.6 * depth);
}
void main() {
  vec2 base = a0.xy;
  if (u_fractions > 0.5) base = vec2((base.x - 0.5) * u_aspect, base.y);
  float angle = a0.z;
  float len = a0.w;
  float width = a1.x;
  float bend = a1.y;
  float depth = a1.z;
  float kind = a1.w;
  float sway = a3.y;
  float blur = mix(u_blurMin, u_blurMax, depth) + u_texel;
  vec2 dir = vec2(cos(angle), sin(angle));
  if (kind > 0.5) {
    // Branch segment: displace both ends with the wind field so neighbouring segments stay joined.
    vec2 end = base + dir * len;
    base += wind(base, depth) * sway;
    end += wind(end, depth) * sway;
    vec2 d = end - base;
    len = max(length(d), 1e-5);
    dir = d / len;
  } else {
    base += wind(base, depth) * sway;
    float flutter = (sin(u_time * (1.9 + a3.w) + a2.w) * 0.1 + sin(u_time * 4.7 + a2.w * 1.7) * 0.035) * u_motion * sway;
    float c = cos(flutter);
    float s = sin(flutter);
    dir = vec2(c * dir.x - s * dir.y, s * dir.x + c * dir.y);
  }
  float reach = kind > 0.5 ? max(width, a3.x) : width * 1.2 + abs(bend) * len * 0.17;
  float margin = blur * 1.2 + u_texel * 2.0;
  int v = gl_VertexID;
  float along = (v < 2) ? -margin - (kind > 0.5 ? width : 0.0) : len + margin + (kind > 0.5 ? a3.x : 0.0);
  float across = ((v & 1) == 0) ? -(reach + margin) : (reach + margin);
  vec2 n = vec2(-dir.y, dir.x);
  vec2 p = base + dir * along + n * across;
  vec2 clip = (p - u_regionMin) / u_regionSize * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  v_local = vec2(along, across);
  v_shape = vec4(len, width, bend, kind);
  v_color = vec4(a2.rgb, a3.z);
  v_misc = vec3(blur, depth, a3.x);
}
`;

export const LEAF_FS = `#version 300 es
${COMMON}
in vec2 v_local;
flat in vec4 v_shape;
flat in vec4 v_color;
flat in vec3 v_misc;
uniform vec3 u_sunRadiance;
uniform vec3 u_ambient;
uniform vec3 u_hazeColor;
uniform float u_haze;
uniform float u_backlight;
uniform float u_veil;        // aerial perspective strength (0 for foreground leaves)
uniform float u_rim;         // edge glow (0 for foreground leaves)
uniform float u_brightness;  // overall scale
out vec4 o;
void main() {
  float len = v_shape.x;
  float w = v_shape.y;
  float blur = v_misc.x;
  float depth = v_misc.y;
  float along = v_local.x;
  float across = v_local.y;
  vec3 albedo = toLinear(v_color.rgb);
  float sd;
  float veins = 0.0;
  float edge = 0.0;
  if (v_shape.w < 0.5) {
    float s = clamp(along / len, 0.0, 1.0);
    float yc = v_shape.z * len * 0.62 * s * (1.0 - s);
    float d = across - yc;
    float halfw = w * 2.62 * pow(s, 0.55) * pow(1.0 - s, 0.9);
    sd = abs(d) - halfw;
    if (along < 0.0) sd = length(vec2(along, d));
    if (along > len) sd = length(vec2(along - len, d));
    // A short petiole.
    sd = min(sd, max(abs(d) - w * 0.07, max(-along - len * 0.08, along - len * 0.05)));
    float sharp = 1.0 - smoothstep(w * 0.12, w * 0.9, blur);
    float mid = smoothstep(w * 0.1, 0.0, abs(d)) * step(0.0, along);
    float lat = abs(fract(s * 10.0 - abs(d) / max(w, 1e-4) * 1.4) - 0.5);
    float latLine = smoothstep(0.06, 0.0, abs(lat - 0.45)) * step(abs(d), halfw * 0.85);
    veins = (mid * 0.75 + latLine * 0.35) * sharp;
    edge = smoothstep(-w * 0.35, 0.0, sd);
  } else {
    float h = clamp(along / len, 0.0, 1.0);
    float r = mix(w, v_misc.z, h);
    sd = length(vec2(along - h * len, across)) - r;
    edge = smoothstep(-r * 0.7, 0.0, sd);
  }
  float cover = smoothstep(blur, -blur, sd);
  if (cover < 0.003) discard;
  float lit = v_color.a;
  vec3 radiance;
  if (v_shape.w < 0.5) {
    // Backlit leaves glow yellow-green through the lamina where the sun reaches them; leaves
    // shaded by others stay dark. Veins read darker; edges catch light.
    vec3 transmit = albedo * vec3(1.3, 1.5, 0.6) + vec3(0.02, 0.035, 0.0);
    radiance = albedo * u_ambient * 0.32;
    radiance += u_sunRadiance * u_backlight * transmit * 0.3 * lit * (1.0 - veins * 0.55);
    radiance += u_sunRadiance * (1.0 - u_backlight) * albedo * 0.5 * lit;
    radiance += u_sunRadiance * u_backlight * edge * 0.04 * lit * lit * u_rim;
  } else {
    radiance = albedo * u_ambient * 0.3 + u_sunRadiance * u_backlight * edge * edge * 0.3 * lit * albedo * 2.0;
  }
  radiance = mix(radiance, u_hazeColor * (0.06 + 0.22 * u_backlight), clamp(depth * u_haze * u_veil * 0.7, 0.0, 0.6));
  float opacity = v_shape.w < 0.5 ? 0.97 : 1.0;
  o = vec4(radiance * u_brightness * cover * opacity, cover * opacity);
}
`;

// Sky, sun and the defocused canopy, at backdrop resolution.
export const BACKDROP_FS = `#version 300 es
${COMMON}
${SPACE}
uniform sampler2D u_canopy;
uniform vec2 u_sunH;
uniform vec3 u_sunRadiance;
uniform vec3 u_skyTop;
uniform vec3 u_skyHorizon;
uniform vec3 u_hazeColor;
uniform float u_haze;
uniform float u_backlight;
uniform float u_sunSize;
uniform vec3 u_ground;     // shaded undergrowth filling the lower stage
in vec2 v_uv;
out vec4 o;
void main() {
  vec2 suv = vec2(v_uv.x, 1.0 - v_uv.y);
  vec2 h = hFromSuv(suv);
  vec3 sky = mix(u_skyTop, u_skyHorizon, smoothstep(-0.3, 0.75, suv.y));
  sky = mix(sky, u_ground, smoothstep(0.3, 1.05, suv.y) * (1.0 - 0.5 * exp(-length(h - u_sunH) / 0.5)));
  float r = length(h - u_sunH);
  float front = smoothstep(0.35, 0.75, u_backlight);
  vec3 aureole = u_sunRadiance * (1.1 * exp(-r / (0.05 * u_sunSize)) + 0.3 * exp(-r / 0.22) + 0.05 * exp(-r / 0.9));
  vec3 col = sky * (0.55 + 0.45 * exp(-r / 0.9)) + aureole * mix(0.2, 1.0, front);
  float discR = 0.016 * u_sunSize;
  col += u_sunRadiance * 36.0 * front * smoothstep(discR * 1.15, discR * 0.85, r);
  col += u_hazeColor * u_haze * (0.03 + 0.3 * exp(-r / 0.45)) * mix(0.4, 1.0, front);
  vec4 canopy = texture(u_canopy, canopyTex(h));
  col = canopy.rgb + col * (1.0 - canopy.a);
  o = vec4(col, 1.0);
}
`;

// Defocused highlights where the sun slips through distant leaves.
export const BOKEH_VS = `#version 300 es
${COMMON}
${SPACE}
layout(location = 0) in vec4 b0; // x, y (stage fractions), radius (h), brightness
layout(location = 1) in vec4 b1; // hue shift, phase, random, spare
uniform sampler2D u_canopy;
uniform vec2 u_sunH;
uniform vec3 u_sunRadiance;
uniform vec3 u_hazeColor;
uniform float u_backlight;
uniform float u_amount;
uniform float u_size;
uniform float u_time;
uniform float u_motion;
out vec2 v_local;
flat out vec3 v_color;
flat out float v_radius;
flat out float v_rot;
void main() {
  vec2 h = hFromSuv(b0.xy);
  h += vec2(sin(u_time * 0.13 + b1.y), cos(u_time * 0.11 + b1.y * 1.3)) * 0.006 * u_motion;
  float gap = 1.0 - textureLod(u_canopy, canopyTex(h), 3.0).a;
  float near = exp(-length(h - u_sunH) / 0.85);
  float bright = b0.w * (0.15 + 0.85 * near) * mix(0.1, 1.0, gap * gap) * u_amount * mix(0.35, 1.0, u_backlight);
  float twinkle = 0.85 + 0.15 * sin(u_time * (0.8 + b1.z) + b1.y * 3.0) * u_motion;
  vec3 tint = mix(u_sunRadiance, u_hazeColor * 1.3, 0.35 + 0.3 * b1.x) * vec3(1.0 + 0.2 * b1.x, 1.0, 1.0 - 0.25 * b1.x);
  v_color = tint * bright * twinkle * 0.45;
  float radius = b0.z * u_size;
  int v = gl_VertexID;
  vec2 corner = vec2((v & 1) == 0 ? -1.2 : 1.2, v < 2 ? -1.2 : 1.2);
  v_local = corner;
  v_radius = radius;
  v_rot = b1.y;
  vec2 p = h + corner * radius;
  vec2 suv = suvFromH(p);
  gl_Position = bright < 0.002 ? vec4(2.0, 2.0, 2.0, 1.0) : vec4(suv.x * 2.0 - 1.0, 1.0 - suv.y * 2.0, 0.0, 1.0);
}
`;

export const BOKEH_FS = `#version 300 es
${COMMON}
in vec2 v_local;
flat in vec3 v_color;
flat in float v_radius;
flat in float v_rot;
uniform float u_blades;
uniform float u_pxPerH;     // backdrop px per h unit
out vec4 o;
float aperture(vec2 q, float scale) {
  q /= scale;
  if (u_blades < 2.5) return length(q) - 1.0;
  float seg = 2.0 * PI / u_blades;
  float a = atan(q.y, q.x) + v_rot;
  float k = mod(a, seg) - seg * 0.5;
  return length(q) * cos(k) / cos(seg * 0.5) - 1.0;
}
void main() {
  float aa = 1.5 / max(v_radius * u_pxPerH, 1.0);
  vec3 d = vec3(aperture(v_local, 1.025), aperture(v_local, 1.0), aperture(v_local, 0.975));
  vec3 disk = smoothstep(aa, -aa, d);
  float rim = 0.72 + 0.5 * smoothstep(-0.35, 0.0, d.g);
  vec3 c = v_color * disk * rim;
  if (max(c.r, max(c.g, c.b)) < 1e-4) discard;
  o = vec4(c, 0.0);
}
`;

// Ray march toward the sun through the canopy's transmission.
// r: in-scattered light fraction along the view (shafts); g: direct sun reaching the web plane (dapples).
export const RAYS_FS = `#version 300 es
${COMMON}
${SPACE}
uniform sampler2D u_canopy;
uniform vec2 u_sunH;
uniform float u_rayLen;
uniform int u_steps;
uniform float u_webDist;
uniform float u_penumbra;
uniform float u_texelH;
uniform float u_jitter;
in vec2 v_uv;
out vec4 o;
float transmission(vec2 h, float lod) {
  vec2 c = (h - u_canopyMin) / u_canopySize;
  if (c.x < 0.0 || c.y < 0.0 || c.x > 1.0 || c.y > 1.0) return 1.0;
  return 1.0 - textureLod(u_canopy, vec2(c.x, 1.0 - c.y), lod).a * 0.97;
}
void main() {
  vec2 suv = vec2(v_uv.x, 1.0 - v_uv.y);
  vec2 h = hFromSuv(suv);
  vec2 toSun = u_sunH - h;
  float dist = length(toSun);
  vec2 dir = toSun / max(dist, 1e-5);
  float len = min(dist, u_rayLen);
  float j = fract(ign(gl_FragCoord.xy) + u_jitter);
  float sum = 0.0;
  float wsum = 0.0;
  for (int i = 0; i < 160; i++) {
    if (i >= u_steps) break;
    float t = (float(i) + j) / float(u_steps);
    float w = 1.0 - 0.55 * t;
    sum += transmission(h + dir * len * t, 1.0) * w;
    wsum += w;
  }
  float inscatter = sum / max(wsum, 1e-5);
  float dWeb = min(dist, u_webDist);
  float lod = log2(max(1.0, u_penumbra * dWeb / u_texelH));
  float vis = transmission(h + dir * dWeb, lod);
  vis *= mix(1.0, transmission(h + dir * dWeb * 1.7, lod + 0.8), 0.45);
  o = vec4(inscatter, vis, 0.0, 1.0);
}
`;

export const BLUR9_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_step;
in vec2 v_uv;
out vec4 o;
void main() {
  vec4 s = texture(u_tex, v_uv) * 0.2270270270;
  s += (texture(u_tex, v_uv + u_step * 1.3846153846) + texture(u_tex, v_uv - u_step * 1.3846153846)) * 0.3162162162;
  s += (texture(u_tex, v_uv + u_step * 3.2307692308) + texture(u_tex, v_uv - u_step * 3.2307692308)) * 0.0702702703;
  o = s;
}
`;

export const COPY_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 o;
void main() { o = texture(u_tex, v_uv); }
`;

// Silk, bark and scaffold lines: the .silk record VBO as instanced capsules, with fibre scattering.
export const SILK_VS = `#version 300 es
layout(location = 0) in vec4 a_seg;
layout(location = 1) in uint a_death;
layout(location = 2) in vec4 a_style;  // kind, width, r, g
layout(location = 3) in vec4 a_style2; // b, lod, flags, alpha
uniform vec3 u_xform;
uniform float u_scale;
uniform float u_dpr;
uniform float u_minLod;
uniform float u_minWidthPx;
uniform float u_coordScale;
uniform float u_widthScale;
uniform float u_thickness;
uniform float u_silkZoom;   // silk stays hair-fine under magnification: zoom^0.3 / zoom
uniform vec2 u_viewport;
uniform float u_cursor;
uniform float u_N;
uniform float u_fadeRecords;
float fadeAt(uint death) {
  if (death == 0xffffffffu) return 1.0;
  float d = float(death);
  if (u_cursor < d) return 1.0;
  float span = max(1.0, min(u_fadeRecords, u_N - d));
  return clamp(1.0 - (u_cursor - d) / span, 0.0, 1.0);
}
flat out vec2 v_a;
flat out vec2 v_b;
flat out float v_radius;
flat out vec4 v_color;   // sRGB, record alpha
flat out float v_cover;  // hairline coverage × death fade
flat out vec4 v_info;    // kind, flags, index, device px per native px
flat out vec2 v_native;  // native coordinates of the segment start
out vec2 v_p;
void main() {
  float index = float(gl_InstanceID);
  int flags = int(a_style2.z);
  float fade = fadeAt(a_death);
  bool visible = index < u_cursor && (flags & 4) == 0 && a_style2.y >= u_minLod && fade > 0.0;
  if (!visible) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_a = vec2(0.0); v_b = vec2(0.0); v_radius = 0.0; v_color = vec4(0.0); v_cover = 0.0; v_info = vec4(0.0); v_native = vec2(0.0); v_p = vec2(0.0);
    return;
  }
  vec2 p0 = a_seg.xy / u_coordScale;
  vec2 p1 = a_seg.zw / u_coordScale;
  float tip = floor(u_cursor);
  if (index == tip) p1 = p0 + (p1 - p0) * (u_cursor - tip);
  vec2 a = u_xform.xy + p0 * u_xform.z;
  vec2 b = u_xform.xy + p1 * u_xform.z;
  bool env = (flags & 2) != 0;
  float wPx = max(a_style.y / u_widthScale * u_scale * (env ? (a_style2.w > 254.0 ? 1.7 : 1.0) : u_thickness * u_silkZoom), u_minWidthPx) * u_dpr;
  float radius = max(0.5 * wPx, 0.5);
  vec2 d = b - a;
  float len = length(d);
  vec2 dir = len > 1e-4 ? d / len : vec2(1.0, 0.0);
  vec2 n = vec2(-dir.y, dir.x);
  float ext = radius + 1.0;
  int v = gl_VertexID;
  vec2 base = (v < 2) ? a - dir * ext : b + dir * ext;
  vec2 p = base + n * ((v & 1) == 0 ? -ext : ext);
  v_a = a; v_b = b; v_radius = radius; v_p = p;
  v_color = vec4(vec3(a_style.z, a_style.w, a_style2.x) / 255.0, a_style2.w / 255.0);
  v_cover = min(wPx, 1.0) * fade;
  v_info = vec4(a_style.x, float(flags), index, u_xform.z);
  v_native = p0;
  gl_Position = vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
}
`;

const LIGHTING = `
uniform sampler2D u_light;   // r: shafts, g: sun visibility on the web plane
uniform vec3 u_sunDir;       // unit, from the web toward the sun
uniform vec3 u_sunRadiance;  // linear
uniform vec3 u_ambient;      // linear sky fill
uniform vec3 u_eye;          // CSS px (stage centre, focal distance)
uniform vec2 u_viewport;
uniform float u_dpr;
uniform vec3 u_view;         // zoom, offset x, offset y (CSS px)
// Light and view directions belong to the unzoomed web plane, so dapples and highlights stay
// fixed to the silk while zooming.
vec2 unzoom(vec2 css) { return (css - u_view.yz) / u_view.x; }
float sunVisibility(vec2 css) {
  vec2 suv = unzoom(css) / (u_viewport / u_dpr);
  return texture(u_light, vec2(suv.x, 1.0 - suv.y)).g;
}
vec3 viewDir(vec2 css) { return normalize(vec3(u_eye.xy - unzoom(css), u_eye.z)); }
`;

export const SILK_FS = `#version 300 es
${COMMON}
${LIGHTING}
flat in vec2 v_a;
flat in vec2 v_b;
flat in float v_radius;
flat in vec4 v_color;
flat in float v_cover;
flat in vec4 v_info;
flat in vec2 v_native;
in vec2 v_p;
uniform float u_brightness;
uniform float u_iridescence;
uniform float u_sheen;
uniform float u_sparkle;
uniform vec3 u_leafTint;
out vec4 o;

// Fibre scattering: a longitudinal lobe peaking where T·S + T·V = 0 (the specular cone of a
// cylinder), reflection (R) and forward transmission (TT) around the fibre, and a small
// wavelength-dependent lobe shift that splits highlights into spectral fringes.
vec3 fibre(vec3 T, vec3 S, vec3 V, float beta, float irid) {
  float tS = dot(T, S);
  float tV = dot(T, V);
  vec3 shift = vec3(-1.0, 0.0, 1.0) * beta * 0.95 * irid;
  vec3 x = (tS + tV + shift) / beta;
  vec3 M = exp(-0.5 * x * x);
  vec3 x2 = (tS + tV + shift * 2.7) / (beta * 1.3);
  M += 0.4 * irid * exp(-0.5 * x2 * x2);
  vec3 sp = S - tS * T;
  vec3 vp = V - tV * T;
  float cphi = dot(sp, vp) / max(length(sp) * length(vp), 1e-4);
  float nR = 0.25 * sqrt(max(0.0, 0.5 + 0.5 * cphi));
  float nTT = pow(max(0.0, 0.5 - 0.5 * cphi), 5.0) * 2.4;
  return M * (nR + nTT) * (0.32 / beta);
}

void main() {
  vec2 pa = v_p - v_a;
  vec2 ba = v_b - v_a;
  float L2 = max(dot(ba, ba), 1e-8);
  float along = clamp(dot(pa, ba) / L2, 0.0, 1.0);
  vec2 perp = pa - ba * along;
  float dist = length(perp);
  float coverage = clamp(v_radius + 0.5 - dist, 0.0, 1.0);
  if (coverage <= 0.0) discard;
  vec2 dir2 = L2 > 1e-6 ? ba / sqrt(L2) : vec2(1.0, 0.0);
  vec2 css = v_p / u_dpr;
  float vis = sunVisibility(css);
  int kind = int(v_info.x + 0.5);
  int flags = int(v_info.y + 0.5);
  float pxPerNative = v_info.w;
  vec3 base = toLinear(v_color.rgb);
  vec3 S = u_sunDir;
  vec3 V = viewDir(css);
  vec3 radiance;
  float opacity;
  float alpha = coverage * v_color.a * v_cover;
  if ((flags & 2) != 0) {
    vec2 nrm2 = vec2(-dir2.y, dir2.x);
    float across = clamp(dot(perp, nrm2) / max(v_radius, 0.5), -1.0, 1.0);
    vec3 N = normalize(vec3(nrm2 * across, sqrt(max(0.0, 1.0 - across * across))));
    float nativeAlong = along * sqrt(L2) / pxPerNative;
    vec2 np = v_native + dir2 * nativeAlong;
    // Leaf margins and veins are warm browns at alpha below 1; the redback's timber and grain are
    // near-neutral greys and are shaded as flat planks rather than round bark.
    float warmth = v_color.r - v_color.b;
    bool leafLine = kind == 0 && v_color.a < 0.95 && warmth > 0.12;
    bool timber = kind == 0 && !leafLine && warmth < 0.12 && abs(v_color.r - v_color.g) < 0.06;
    if (timber) N = normalize(vec3(nrm2 * across * 0.35, 1.0));
    if (leafLine) {
      // Margins and veins of scaffold leaves: fine lines over the translucent fill.
      vec3 tint = u_leafTint * (0.55 + 0.45 * vis);
      radiance = tint * (u_ambient * 0.35 + u_sunRadiance * vis * 0.25);
      opacity = 0.7;
    } else {
      float grain = fbm(vec2(dot(np, dir2) * 0.06, dot(np, nrm2) * 0.8));
      float furrow = smoothstep(0.35, 0.75, vnoise(vec2(dot(np, dir2) * 0.02, dot(np, nrm2) * 1.6 + 3.0)));
      vec3 albedo = base * (0.7 + 0.55 * grain) * (1.0 - 0.25 * furrow);
      float ndl = dot(N, S);
      float wrap = max(0.0, (ndl + 0.3) / 1.3);
      vec3 amb = u_ambient * (0.3 + 0.3 * (1.0 - N.z));
      radiance = albedo * (amb + u_sunRadiance * vis * wrap);
      // Backlit rim where the bark's silhouette faces the sun.
      vec2 facing = N.xy / max(length(N.xy), 1e-4);
      vec2 sunXY = S.xy / max(length(S.xy), 1e-4);
      float rim = pow(max(0.0, dot(facing, sunXY)), 2.0) * pow(1.0 - N.z, 2.5) * max(0.0, -S.z) * (1.0 - grain * 0.4);
      radiance += u_sunRadiance * vis * rim * (albedo * 2.5 + 0.08);
      opacity = 1.0;
    }
  } else {
    vec3 T = vec3(dir2, 0.0);
    float beta = mix(0.035, 0.32, u_sheen);
    float diffuse = 0.1;
    float irid = u_iridescence;
    if (kind == 8 || kind == 9 || kind == 12 || kind == 14) {
      // Stabilimentum, tufts, retreat and cribellate wool: dense, matt silk.
      beta *= 2.6;
      diffuse = kind == 14 ? 0.3 : 0.45;
      irid *= 0.35;
    } else if (kind == 10 || kind == 1) {
      beta *= 3.0;
      diffuse = 0.5;
      irid = 0.0;
    }
    vec3 spec = fibre(T, S, V, beta, irid);
    vec3 tint = mix(vec3(1.0), base, 0.45);
    radiance = base * u_ambient * 0.3;
    radiance += u_sunRadiance * vis * u_brightness * (base * diffuse + spec * tint);
    if ((flags & 1) != 0) {
      // Glue droplets on capture silk glint regardless of thread direction.
      float spacing = 3.4;
      float s = along * sqrt(L2) / pxPerNative;
      float k = fract(s / spacing + hash11(v_info.z * 0.7548776662));
      float bead = exp(-pow((k - 0.5) * 6.0, 2.0));
      bead = mix(0.42, bead, smoothstep(1.6, 4.5, spacing * pxPerNative));
      radiance += u_sunRadiance * vis * bead * u_sparkle * 0.8 * tint;
    }
    opacity = 0.18;
  }
  o = vec4(radiance * alpha, alpha * opacity);
}
`;

// Filled leaves and egg sacs rebuilt from their closed outline records (see leafMesh.js).
export const LEAFMESH_VS = `#version 300 es
layout(location = 0) in vec2 a_pos;   // native px
layout(location = 1) in vec4 a_leaf;  // s (base to tip), t (across), birth record, shape id
layout(location = 2) in vec4 a_extra; // material, r, g, b
uniform vec3 u_xform;
uniform vec2 u_viewport;
uniform float u_cursor;
out vec2 v_st;
out vec2 v_p;
flat out float v_id;
flat out float v_fade;
flat out vec4 v_extra;
void main() {
  float fade = clamp((u_cursor - a_leaf.z) / 24.0, 0.0, 1.0);
  vec2 p = u_xform.xy + a_pos * u_xform.z;
  v_st = a_leaf.xy;
  v_p = p;
  v_id = a_leaf.w;
  v_fade = fade;
  v_extra = a_extra;
  gl_Position = fade <= 0.0 ? vec4(2.0, 2.0, 2.0, 1.0) : vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
}
`;

export const LEAFMESH_FS = `#version 300 es
${COMMON}
${LIGHTING}
in vec2 v_st;
in vec2 v_p;
flat in float v_id;
flat in float v_fade;
flat in vec4 v_extra;
uniform vec3 u_leafTint;
out vec4 o;
void main() {
  float s = v_st.x;
  float t = v_st.y;
  float h = hash11(v_id * 1.618 + 0.37);
  vec2 css = v_p / u_dpr;
  float vis = sunVisibility(css);
  vec3 S = u_sunDir;
  float back = max(0.0, -S.z);
  vec3 radiance;
  float a;
  if (v_extra.x > 1.5) {
    // Egg sac: a ball of woolly silk that glows through when backlit.
    vec3 base = toLinear(v_extra.yzw);
    vec2 q = vec2((s - 0.5) * 2.0, t);
    float r = clamp(length(q), 0.0, 1.0);
    float nz = sqrt(1.0 - r * r);
    float wool = fbm(v_st * vec2(9.0, 5.0) + v_id * 3.7);
    float strands = 0.5 + 0.5 * sin((s * 26.0 + t * 7.0) + wool * 6.0);
    vec3 silk = base * (0.75 + 0.5 * wool) * (0.85 + 0.25 * strands);
    radiance = silk * u_ambient * (0.45 + 0.35 * nz);
    radiance += u_sunRadiance * vis * silk * (0.18 + 0.55 * back * (0.4 + 0.6 * (1.0 - nz)) + 0.5 * max(0.0, S.z) * nz);
    a = 0.94 * v_fade;
  } else {
    float mid = smoothstep(0.07, 0.0, abs(t));
    float lat = abs(fract(s * 9.0 - abs(t) * 1.3) - 0.5);
    float veins = mid * 0.8 + smoothstep(0.05, 0.0, abs(lat - 0.46)) * 0.4 * step(abs(t), 0.85);
    vec3 albedo = u_leafTint * (0.8 + 0.4 * h) * vec3(1.0 + 0.2 * (h - 0.5), 1.0, 1.0 - 0.3 * (h - 0.5));
    // The hauled leaf is dead and dry.
    if (v_extra.x > 0.5) albedo = vec3(0.3, 0.19, 0.09) * (0.85 + 0.3 * vnoise(v_st * vec2(14.0, 4.0) + v_id));
    albedo *= 0.9 + 0.2 * vnoise(v_st * vec2(18.0, 6.0) + v_id * 7.0);
    vec3 transmit = albedo * vec3(1.3, 1.5, 0.65) + vec3(0.02, 0.04, 0.0);
    radiance = albedo * u_ambient * 0.5;
    radiance += u_sunRadiance * vis * back * transmit * 0.5 * (1.0 - veins * 0.5);
    radiance += u_sunRadiance * vis * max(0.0, S.z) * albedo * 0.8 * (1.0 - veins * 0.2);
    float edge = smoothstep(0.65, 1.0, abs(t));
    radiance *= 1.0 - 0.25 * edge;
    a = 0.96 * v_fade;
  }
  o = vec4(radiance * a, a);
}
`;

// Dew and glue as ball lenses: exact two-surface refraction of the backdrop (an inverted image),
// per-channel dispersion, Fresnel reflection, the sun's specular glint and the sun seen through
// the drop.
export const DEW_VS = `#version 300 es
layout(location = 0) in vec3 a_bead;      // x, y, r (native px)
layout(location = 1) in uvec2 a_host;     // host index, host death
layout(location = 2) in vec4 a_hostColor; // r, g, b, alpha (normalized)
layout(location = 3) in vec4 a_meta;      // host lod, host flags, bead flags, 0
layout(location = 4) in float a_u;        // dew delay fraction
uniform vec3 u_xform;
uniform vec2 u_viewport;
uniform float u_minLod;
uniform float u_dewAge;
uniform float u_cursor;
uniform float u_N;
uniform float u_fadeRecords;
uniform float u_amount;
uniform float u_size;
float fadeAt(uint death) {
  if (death == 0xffffffffu) return 1.0;
  float d = float(death);
  if (u_cursor < d) return 1.0;
  float span = max(1.0, min(u_fadeRecords, u_N - d));
  return clamp(1.0 - (u_cursor - d) / span, 0.0, 1.0);
}
flat out vec2 v_center;
flat out float v_r;
flat out vec4 v_kind;   // glue, lure, alpha, satellite
out vec2 v_p;
void main() {
  int hostFlags = int(a_meta.y);
  int beadFlags = int(a_meta.z);
  float fade = fadeAt(a_host.y);
  bool glue = (beadFlags & 2) != 0;
  float progress = 1.0;
  float size = 1.0;
  if (!glue) {
    float t = u_dewAge < 0.0 ? 0.0 : clamp((u_dewAge - 2.4 * a_u) / 0.35, 0.0, 1.0);
    progress = 1.0 - pow(1.0 - t, 3.0);
    // A second hash decides which droplets form at all, so Amount thins dew evenly.
    float keep = fract(a_u * 7.31 + 0.137 * float(gl_InstanceID % 97));
    if (keep >= u_amount) progress = 0.0;
    size = u_size;
  }
  bool visible = float(a_host.x) < floor(u_cursor) && progress > 0.0 && (hostFlags & 4) == 0 &&
    a_meta.x >= u_minLod && fade > 0.0 && a_bead.z > 0.0;
  if (!visible) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_center = vec2(0.0); v_r = 0.0; v_kind = vec4(0.0); v_p = vec2(0.0);
    return;
  }
  vec2 c = u_xform.xy + a_bead.xy * u_xform.z;
  float r = max(a_bead.z * progress * size * u_xform.z, 0.6);
  float ext = r + 1.5;
  int v = gl_VertexID;
  vec2 p = c + vec2((v & 1) == 0 ? -ext : ext, v < 2 ? -ext : ext);
  v_center = c;
  v_r = r;
  v_kind = vec4(glue ? 1.0 : 0.0, (beadFlags & 4) != 0 ? 1.0 : 0.0, a_hostColor.a * fade * min(1.0, progress * 1.5), (beadFlags & 1) != 0 ? 1.0 : 0.0);
  v_p = p;
  gl_Position = vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
}
`;

export const DEW_FS = `#version 300 es
${COMMON}
${LIGHTING}
flat in vec2 v_center;
flat in float v_r;
flat in vec4 v_kind;
in vec2 v_p;
uniform sampler2D u_backdrop;
uniform float u_refraction;
uniform float u_glint;
uniform float u_lensDist;   // device px from the drop to the imaged scene
uniform vec3 u_skyTop;
uniform vec3 u_skyHorizon;
out vec4 o;

vec3 exitDir(vec3 N, float eta) {
  vec3 I = vec3(0.0, 0.0, -1.0);
  vec3 r1 = refract(I, N, 1.0 / eta);
  float tExit = -2.0 * dot(N, r1);
  vec3 P1 = N + r1 * tExit;
  vec3 r2 = refract(r1, -P1, eta);
  if (dot(r2, r2) < 1e-6) r2 = reflect(r1, -P1);
  return normalize(r2);
}

vec3 scene(vec2 devicePx, float lod) {
  vec2 uv = devicePx / u_viewport;
  return textureLod(u_backdrop, vec2(uv.x, 1.0 - uv.y), lod).rgb;
}

void main() {
  vec2 q = (v_p - v_center) / v_r;
  float r2 = dot(q, q);
  float cover = clamp((v_r - length(v_p - v_center)) + 0.5, 0.0, 1.0);
  if (cover <= 0.0) discard;
  float z = sqrt(max(0.0, 1.0 - min(r2, 1.0)));
  vec3 N = vec3(q, z);
  vec2 css = v_center / u_dpr;
  float vis = sunVisibility(css);
  vec3 S = u_sunDir;
  bool glue = v_kind.x > 0.5;
  // The drop images a wide field of the scene behind it, upside down.
  float strength = u_refraction;
  vec3 dR = exitDir(N, 1.3290);
  vec3 dG = exitDir(N, 1.3330);
  vec3 dB = exitDir(N, 1.3390);
  float lod = 1.5;
  vec3 refr;
  refr.r = scene(v_center + dR.xy / max(0.3, -dR.z) * u_lensDist * strength + q * v_r * (1.0 - strength), lod).r;
  refr.g = scene(v_center + dG.xy / max(0.3, -dG.z) * u_lensDist * strength + q * v_r * (1.0 - strength), lod).g;
  refr.b = scene(v_center + dB.xy / max(0.3, -dB.z) * u_lensDist * strength + q * v_r * (1.0 - strength), lod).b;
  // The sun seen through the lens: a hot caustic on the side away from the sun.
  float through = pow(max(0.0, dot(dG, S)), 180.0) * 60.0 + pow(max(0.0, dot(dG, S)), 12.0) * 1.2;
  vec3 R = reflect(vec3(0.0, 0.0, -1.0), N);
  float fresnel = 0.02 + 0.98 * pow(1.0 - z, 5.0);
  vec3 env = mix(u_skyHorizon, u_skyTop, clamp(-R.y * 0.5 + 0.5, 0.0, 1.0)) * 0.8 + u_ambient * 0.3;
  float glint = pow(max(0.0, dot(R, S)), 900.0) * 400.0 + pow(max(0.0, dot(R, S)), 40.0) * 2.0;
  vec3 water = glue ? vec3(1.0, 0.86, 0.55) : vec3(0.97, 1.0, 1.02);
  vec3 col = refr * water * (1.0 - fresnel);
  col += env * fresnel;
  col += u_sunRadiance * vis * u_glint * (glint * mix(1.0, 0.5, fresnel) + through * (1.0 - fresnel) * water);
  // Total internal reflection darkens the rim.
  col *= mix(1.0, 0.25, smoothstep(0.72, 1.0, r2));
  col += u_sunRadiance * vis * 0.25 * smoothstep(0.85, 1.0, r2) * max(0.0, dot(normalize(q + 1e-4), normalize(S.xy + 1e-4)));
  float a = cover * v_kind.z;
  o = vec4(col * a, a);
}
`;

// Motes drifting through the light shafts; defocused ones become soft discs.
export const MOTE_VS = `#version 300 es
${COMMON}
layout(location = 0) in vec4 m0; // x, y (stage fractions), depth, size
layout(location = 1) in vec4 m1; // phase, speed, random, spare
uniform sampler2D u_light;
uniform vec2 u_stage;
uniform float u_dpr;
uniform float u_time;
uniform float u_motion;
uniform float u_amount;
uniform vec3 u_sunRadiance;
out vec2 v_local;
flat out vec3 v_color;
flat out float v_soft;
void main() {
  float t = u_time * m1.y;
  vec2 pos = m0.xy + vec2(sin(t * 0.13 + m1.x) * 0.02 + t * 0.0025, -t * 0.004 + sin(t * 0.21 + m1.x * 2.0) * 0.012) * u_motion;
  pos = fract(pos);
  float lit = texture(u_light, vec2(pos.x, 1.0 - pos.y)).r;
  lit = pow(lit, 3.0);
  float depth = m0.z;
  float blurPx = abs(depth) * 9.0 * u_dpr;
  float corePx = (0.6 + m0.w * 0.9) * u_dpr;
  float radius = corePx + blurPx;
  float energy = corePx * corePx / (radius * radius);
  float twinkle = 0.6 + 0.4 * sin(u_time * (2.0 + m1.z * 3.0) + m1.x * 5.0);
  v_color = u_sunRadiance * lit * u_amount * energy * twinkle * 2.2;
  v_soft = blurPx / radius;
  int v = gl_VertexID;
  vec2 corner = vec2((v & 1) == 0 ? -1.0 : 1.0, v < 2 ? -1.0 : 1.0);
  v_local = corner;
  vec2 device = pos * u_stage * u_dpr + corner * (radius + 1.0);
  vec2 viewport = u_stage * u_dpr;
  gl_Position = (lit * u_amount < 0.004) ? vec4(2.0, 2.0, 2.0, 1.0) : vec4(device.x / viewport.x * 2.0 - 1.0, 1.0 - device.y / viewport.y * 2.0, 0.0, 1.0);
}
`;

export const MOTE_FS = `#version 300 es
precision highp float;
in vec2 v_local;
flat in vec3 v_color;
flat in float v_soft;
out vec4 o;
void main() {
  float d = length(v_local);
  float disk = 1.0 - smoothstep(1.0 - max(v_soft, 0.35), 1.0, d);
  if (disk <= 0.0) discard;
  o = vec4(v_color * disk, 0.0);
}
`;

// Bloom: 13-tap downsample with soft threshold (first level Karis-averaged), tent upsample.
export const BLOOM_DOWN_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_texel;     // source texel size
uniform float u_prefilter;
uniform float u_threshold;
uniform float u_knee;
in vec2 v_uv;
out vec4 o;
vec3 soft(vec3 c) {
  float br = max(c.r, max(c.g, c.b));
  float rq = clamp(br - u_threshold + u_knee, 0.0, 2.0 * u_knee);
  rq = rq * rq / (4.0 * u_knee + 1e-4);
  float w = max(rq, br - u_threshold) / max(br, 1e-4);
  return c * w;
}
void main() {
  vec2 t = u_texel;
  vec3 a = texture(u_tex, v_uv + t * vec2(-2, -2)).rgb;
  vec3 b = texture(u_tex, v_uv + t * vec2(0, -2)).rgb;
  vec3 c = texture(u_tex, v_uv + t * vec2(2, -2)).rgb;
  vec3 d = texture(u_tex, v_uv + t * vec2(-2, 0)).rgb;
  vec3 e = texture(u_tex, v_uv).rgb;
  vec3 f = texture(u_tex, v_uv + t * vec2(2, 0)).rgb;
  vec3 g = texture(u_tex, v_uv + t * vec2(-2, 2)).rgb;
  vec3 h = texture(u_tex, v_uv + t * vec2(0, 2)).rgb;
  vec3 i = texture(u_tex, v_uv + t * vec2(2, 2)).rgb;
  vec3 j = texture(u_tex, v_uv + t * vec2(-1, -1)).rgb;
  vec3 k = texture(u_tex, v_uv + t * vec2(1, -1)).rgb;
  vec3 l = texture(u_tex, v_uv + t * vec2(-1, 1)).rgb;
  vec3 m = texture(u_tex, v_uv + t * vec2(1, 1)).rgb;
  // No Karis weighting: single-pixel dew glints are meant to bloom, and the scene is nearly static.
  vec3 color = e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
  if (u_prefilter > 0.5) color = soft(color);
  o = vec4(color, 1.0);
}
`;

export const BLOOM_UP_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_texel;
uniform float u_radius;
uniform float u_weight;
in vec2 v_uv;
out vec4 o;
void main() {
  vec2 t = u_texel * u_radius;
  vec3 s = texture(u_tex, v_uv).rgb * 4.0;
  s += (texture(u_tex, v_uv + vec2(-t.x, 0.0)).rgb + texture(u_tex, v_uv + vec2(t.x, 0.0)).rgb +
        texture(u_tex, v_uv + vec2(0.0, -t.y)).rgb + texture(u_tex, v_uv + vec2(0.0, t.y)).rgb) * 2.0;
  s += texture(u_tex, v_uv + vec2(-t.x, -t.y)).rgb + texture(u_tex, v_uv + vec2(t.x, -t.y)).rgb +
       texture(u_tex, v_uv + vec2(-t.x, t.y)).rgb + texture(u_tex, v_uv + vec2(t.x, t.y)).rgb;
  o = vec4(s / 16.0 * u_weight, 1.0);
}
`;

// Quarter-resolution box average of the scene that keeps isolated glints for the star filter.
export const BRIGHT_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_texel;   // source texel size
in vec2 v_uv;
out vec4 o;
void main() {
  vec3 s = texture(u_tex, v_uv + u_texel * vec2(-1.0, -1.0)).rgb + texture(u_tex, v_uv + u_texel * vec2(1.0, -1.0)).rgb +
           texture(u_tex, v_uv + u_texel * vec2(-1.0, 1.0)).rgb + texture(u_tex, v_uv + u_texel * vec2(1.0, 1.0)).rgb;
  o = vec4(s * 0.25, 1.0);
}
`;

// Star filter: a directional streak blur of the brightest glints, three passes per axis.
export const STREAK_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_dir;        // texel step along the streak
uniform float u_pass;      // 0, 1, 2
uniform float u_threshold;
in vec2 v_uv;
out vec4 o;
void main() {
  float stride = pow(3.0, u_pass);
  vec3 s = vec3(0.0);
  float wsum = 0.0;
  for (int k = -3; k <= 3; k++) {
    float fk = float(k);
    float w = pow(0.86, abs(fk) * stride);
    vec3 c = texture(u_tex, v_uv + u_dir * fk * stride).rgb;
    if (u_pass < 0.5) c = max(c - u_threshold, 0.0);
    s += c * w;
    wsum += w;
  }
  // Keep the centre's energy along the streak rather than spreading it thin.
  o = vec4(s / sqrt(wsum), 1.0);
}
`;

// Final grade: shafts, bloom, stars, foreground leaves and lens ghosts over the scene, then
// exposure, white balance, ACES filmic tone mapping, contrast, saturation, vignette, grain, sRGB.
export const COMPOSITE_FS = `#version 300 es
${COMMON}
${SPACE}
uniform sampler2D u_scene;
uniform sampler2D u_bloomTex;
uniform sampler2D u_starTex;
uniform sampler2D u_light;
uniform sampler2D u_foreground;
uniform sampler2D u_canopy;
uniform vec2 u_sunH;
uniform vec3 u_sunRadiance;
uniform vec3 u_hazeColor;
uniform vec3 u_sunDir;
uniform float u_haze;
uniform float u_rays;
uniform float u_backlight;
uniform float u_bloom;
uniform float u_star;
uniform float u_exposure;
uniform float u_contrast;
uniform float u_saturation;
uniform vec3 u_whiteBalance;
uniform float u_splitTone;
uniform float u_vignette;
uniform float u_grain;
uniform float u_aberration;
uniform float u_flare;
uniform float u_time;
uniform float u_foregroundOn;
uniform float u_eyeZ;         // focal distance in h units
uniform float u_debug;        // 1 shafts, 2 sun visibility, 3 canopy coverage, 4 bloom, 5 stars
uniform float u_spikes;       // diffraction spikes from the aperture blades (0: round)
uniform float u_sunSize;
in vec2 v_uv;
out vec4 o;
vec3 aces(vec3 x) {
  const float a = 2.51;
  const float b = 0.03;
  const float c = 2.43;
  const float d = 0.59;
  const float e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}
vec3 toSrgb(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
float phaseHG(float cosTheta, float g) {
  float d = 1.0 + g * g - 2.0 * g * cosTheta;
  return pow((1.0 - g) * (1.0 - g) / d, 1.5);
}
void main() {
  vec2 uv = v_uv;
  vec2 suv = vec2(uv.x, 1.0 - uv.y);
  if (u_debug > 0.5) {
    vec2 hd = hFromSuv(suv);
    if (u_debug > 3.5) {
      o = vec4(sqrt((u_debug < 4.5 ? texture(u_bloomTex, uv).rgb : texture(u_starTex, uv).rgb) * 0.25), 1.0);
      return;
    }
    float value = u_debug < 1.5 ? texture(u_light, uv).r : u_debug < 2.5 ? texture(u_light, uv).g : textureLod(u_canopy, canopyTex(hd), 0.0).a;
    o = vec4(vec3(value), 1.0);
    return;
  }
  vec2 fromCentre = uv - 0.5;
  vec2 ca = fromCentre * u_aberration * 0.006;
  vec3 col;
  col.r = texture(u_scene, uv - ca).r;
  col.g = texture(u_scene, uv).g;
  col.b = texture(u_scene, uv + ca).b;
  // In-scattered sunlight: forward-scattering phase function times the marched shaft fraction.
  vec2 h = hFromSuv(suv);
  vec3 view = normalize(vec3(h.x, h.y - 0.5, -u_eyeZ));
  float cosT = dot(view, u_sunDir);
  float phase = 0.12 + phaseHG(cosT, 0.72) * 0.9 + phaseHG(cosT, 0.25) * 0.25;
  float shafts = texture(u_light, uv).r;
  // Beams stand out where the march found open air between shaded stretches: stretch the marched
  // fraction into a beam mask, and keep a little uniform glow for air with no occluders at all.
  float beam = smoothstep(0.1, 0.55, shafts);
  vec3 airlight = mix(u_sunRadiance, u_hazeColor * luma(u_sunRadiance) * 1.4, 0.35);
  col = col * (1.0 - u_haze * 0.12) + airlight * (0.12 * shafts + beam * beam) * phase * u_haze * u_rays * 0.7;
  // Sun glare: veiling glare and aperture diffraction spikes, scaled by how much sun the canopy lets through.
  vec2 sd = h - u_sunH;
  float sr = length(sd);
  float front = smoothstep(0.4, 0.8, u_backlight);
  float sunOpen = (1.0 - 0.85 * textureLod(u_canopy, canopyTex(u_sunH), 3.5).a) * front;
  float glare = 1.4 * exp(-sr / (0.012 * u_sunSize)) + 0.3 * exp(-sr / 0.06) + 0.07 * exp(-sr / 0.25);
  float spike = 0.0;
  if (u_spikes > 0.5) {
    float ang = atan(sd.y, sd.x);
    float fan = pow(abs(cos(ang * u_spikes * 0.5 + 0.35)), 180.0);
    spike = fan * (0.5 * exp(-sr / 0.05) + 0.2 * exp(-sr / 0.22)) * u_flare * 2.5;
  }
  col += u_sunRadiance * sunOpen * (glare + spike) * 0.6;
  col += texture(u_bloomTex, uv).rgb * u_bloom * 0.9;
  col += texture(u_starTex, uv).rgb * u_star;
  if (u_foregroundOn > 0.5) {
    vec4 fg = texture(u_foreground, uv);
    col = fg.rgb + col * (1.0 - fg.a);
  }
  if (u_flare > 0.0) {
    // Lens ghosts mirrored through the centre, strongest when the sun itself is unobstructed.
    vec2 sunSuv = suvFromH(u_sunH);
    vec2 cc = vec2(0.5);
    float onScreen = smoothstep(0.35, 0.0, max(max(-sunSuv.x, sunSuv.x - 1.0), max(-sunSuv.y, sunSuv.y - 1.0)));
    vec2 tc = canopyTex(u_sunH);
    float open = 1.0 - textureLod(u_canopy, tc, 4.0).a;
    float strength = u_flare * onScreen * open * smoothstep(0.4, 0.8, u_backlight);
    vec3 ghosts = vec3(0.0);
    float aspect = u_stage.x / u_stage.y;
    for (int k = 0; k < 5; k++) {
      float f = float(k);
      float t = -0.35 - f * 0.42;
      vec2 gpos = cc + (sunSuv - cc) * t;
      float size = 0.02 + 0.035 * fract(f * 0.618 + 0.3);
      vec2 dd = (suv - gpos) * vec2(aspect, 1.0);
      float g = smoothstep(size, size * 0.6, length(dd));
      vec3 tint = 0.5 + 0.5 * cos(6.2831 * (f * 0.21 + vec3(0.0, 0.33, 0.67)));
      ghosts += tint * g * (0.12 + 0.1 * fract(f * 0.37));
    }
    vec2 hd = (suv - sunSuv) * vec2(aspect, 1.0);
    float halo = exp(-pow((length(hd) - 0.28) / 0.02, 2.0)) * 0.12;
    col += u_sunRadiance * strength * (ghosts + halo * vec3(0.9, 0.95, 1.0));
  }
  col *= exp2(u_exposure) * u_whiteBalance;
  col = aces(col);
  float y = luma(col);
  // Split tone: shadows lean teal and highlights amber at unchanged luminance, which keeps green
  // foliage under a warm sun from settling into one olive middle tone.
  vec3 tint = mix(vec3(0.8, 1.0, 1.2), vec3(1.12, 1.0, 0.8), smoothstep(0.02, 0.4, y));
  vec3 toned = col * tint;
  col = mix(col, toned * (y / max(luma(toned), 1e-5)), u_splitTone);
  col = mix(vec3(y), col, u_saturation);
  // Contrast as a power curve about mid-grey: a linear pivot at 0.5 would clip every channel
  // below 0.05 to black and strip the blue from the shade.
  col = clamp(0.18 * pow(max(col, vec3(0.0)) / 0.18, vec3(u_contrast)), 0.0, 1.0);
  float vig = length(fromCentre * vec2(1.0, u_stage.y / u_stage.x) * 1.35);
  col *= 1.0 - u_vignette * smoothstep(0.35, 1.05, vig) * 0.75;
  vec3 srgb = toSrgb(col);
  float n = hash12(gl_FragCoord.xy + fract(u_time * 13.1) * 97.0) - 0.5;
  srgb += n * u_grain * 0.09 * (1.0 - 0.7 * luma(srgb));
  srgb += (ign(gl_FragCoord.xy) - 0.5) / 255.0;
  o = vec4(clamp(srgb, 0.0, 1.0), 1.0);
}
`;
