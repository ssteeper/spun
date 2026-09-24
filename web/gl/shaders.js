// GLSL ES 3.00 sources for the WebGL2 backend. Semantics mirror render2d.js (§9.3).

const DEVICE_TO_CLIP = `
uniform vec2 u_viewport; // device px
vec4 toClip(vec2 p) {
  return vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
}
`;

const FADE = `
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
`;

export const RECORD_VS = `#version 300 es
layout(location = 0) in vec4 a_seg;    // x0 y0 x1 y1 in coordScale units
layout(location = 1) in uint a_death;
layout(location = 2) in vec4 a_style;  // kind, width, r, g
layout(location = 3) in vec4 a_style2; // b, lod, flags, alpha
uniform vec3 u_xform;       // device origin x, y, device px per native px (s·dpr)
uniform float u_scale;      // CSS px per native px (s)
uniform float u_dpr;
uniform float u_minLod;
uniform float u_minWidthPx; // 0.55
uniform float u_coordScale; // 4
uniform float u_widthScale; // 32
${DEVICE_TO_CLIP}
${FADE}
flat out vec2 v_a;
flat out vec2 v_b;
flat out float v_radius;
flat out vec4 v_color; // premultiplied
out vec2 v_p;

void main() {
  float index = float(gl_InstanceID);
  int flags = int(a_style2.z);
  float fade = fadeAt(a_death);
  bool visible = index < u_cursor && (flags & 4) == 0 && a_style2.y >= u_minLod && fade > 0.0;
  if (!visible) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_a = vec2(0.0); v_b = vec2(0.0); v_radius = 0.0; v_color = vec4(0.0); v_p = vec2(0.0);
    return;
  }
  vec2 p0 = a_seg.xy / u_coordScale;
  vec2 p1 = a_seg.zw / u_coordScale;
  float tip = floor(u_cursor);
  if (index == tip) p1 = p0 + (p1 - p0) * (u_cursor - tip);
  vec2 a = u_xform.xy + p0 * u_xform.z;
  vec2 b = u_xform.xy + p1 * u_xform.z;
  float wPx = max(a_style.y / u_widthScale * u_scale, u_minWidthPx) * u_dpr;
  float radius = max(0.5 * wPx, 0.5);
  float alpha = a_style2.w / 255.0 * min(wPx, 1.0) * fade;
  vec2 d = b - a;
  float len = length(d);
  vec2 dir = len > 1e-4 ? d / len : vec2(1.0, 0.0);
  vec2 n = vec2(-dir.y, dir.x);
  float ext = radius + 1.0;
  int v = gl_VertexID;
  vec2 base = (v < 2) ? a - dir * ext : b + dir * ext;
  vec2 p = base + n * ((v & 1) == 0 ? -ext : ext);
  v_a = a; v_b = b; v_radius = radius;
  v_color = vec4(vec3(a_style.z, a_style.w, a_style2.x) / 255.0 * alpha, alpha);
  v_p = p;
  gl_Position = toClip(p);
}
`;

export const RECORD_FS = `#version 300 es
precision highp float;
flat in vec2 v_a;
flat in vec2 v_b;
flat in float v_radius;
flat in vec4 v_color;
in vec2 v_p;
out vec4 o_color;
void main() {
  vec2 pa = v_p - v_a;
  vec2 ba = v_b - v_a;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-8), 0.0, 1.0);
  float d = length(pa - ba * h);
  float coverage = clamp(v_radius + 0.5 - d, 0.0, 1.0);
  if (coverage <= 0.0) discard;
  o_color = v_color * coverage;
}
`;

export const BEAD_VS = `#version 300 es
layout(location = 0) in vec3 a_bead;      // x, y, r (native px)
layout(location = 1) in uvec2 a_host;     // host index, host death
layout(location = 2) in vec4 a_hostColor; // r, g, b, alpha (normalized bytes)
layout(location = 3) in vec4 a_meta;      // host lod, host flags, bead flags, 0
uniform vec3 u_xform;
uniform float u_minLod;
${DEVICE_TO_CLIP}
${FADE}
flat out vec2 v_center;
flat out float v_r;
flat out vec4 v_hostColor;
flat out float v_alpha;
out vec2 v_p;
void main() {
  int hostFlags = int(a_meta.y);
  int beadFlags = int(a_meta.z);
  float fade = fadeAt(a_host.y);
  bool visible = float(a_host.x) < floor(u_cursor) && (beadFlags & 2) != 0 && (hostFlags & 4) == 0 &&
    a_meta.x >= u_minLod && fade > 0.0 && a_bead.z > 0.0;
  if (!visible) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_center = vec2(0.0); v_r = 0.0; v_hostColor = vec4(0.0); v_alpha = 0.0; v_p = vec2(0.0);
    return;
  }
  vec2 c = u_xform.xy + a_bead.xy * u_xform.z;
  float r = a_bead.z * u_xform.z;
  float ext = r + 1.5;
  int v = gl_VertexID;
  vec2 p = c + vec2((v & 1) == 0 ? -ext : ext, v < 2 ? -ext : ext);
  v_center = c; v_r = r; v_hostColor = a_hostColor; v_alpha = a_hostColor.a * fade; v_p = p;
  gl_Position = toClip(p);
}
`;

export const BEAD_FS = `#version 300 es
precision highp float;
flat in vec2 v_center;
flat in float v_r;
flat in vec4 v_hostColor;
flat in float v_alpha;
in vec2 v_p;
out vec4 o_color;
vec4 over(vec4 top, vec4 under) { return top + under * (1.0 - top.a); }
void main() {
  float d = length(v_p - v_center);
  float core = clamp(v_r + 0.5 - d, 0.0, 1.0) * 0.35 * v_alpha;
  vec4 color = vec4(v_hostColor.rgb * core, core);
  float rimPx = 0.12 * v_r;
  float rim = clamp(0.5 * max(rimPx, 1.0) + 0.5 - abs(d - 0.85 * v_r), 0.0, 1.0) * min(rimPx, 1.0) * 0.86 * 0.85 * v_alpha;
  color = over(vec4(rim), color);
  float glint = clamp(0.28 * v_r + 0.5 - length(v_p - (v_center - 0.35 * v_r)), 0.0, 1.0) * v_alpha;
  color = over(vec4(glint), color);
  if (color.a <= 0.0) discard;
  o_color = color;
}
`;

export const QUAD_VS = `#version 300 es
out vec2 v_uv;
void main() {
  vec2 p = vec2((gl_VertexID & 1) == 0 ? -1.0 : 1.0, gl_VertexID < 2 ? -1.0 : 1.0);
  v_uv = p * 0.5 + 0.5;
  gl_Position = vec4(p, 0.0, 1.0);
}
`;

export const COPY_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform float u_gain;
in vec2 v_uv;
out vec4 o_color;
void main() { o_color = texture(u_tex, v_uv) * u_gain; }
`;

// 13 bilinear taps: centre + 6 paired taps per side covering ±12 texels.
export const BLUR_FS = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec2 u_step;       // one texel along the blur axis, in UV
uniform float u_offsets[7];
uniform float u_weights[7];
in vec2 v_uv;
out vec4 o_color;
void main() {
  vec4 sum = texture(u_tex, v_uv) * u_weights[0];
  for (int k = 1; k < 7; k++) {
    vec2 o = u_step * u_offsets[k];
    sum += (texture(u_tex, v_uv + o) + texture(u_tex, v_uv - o)) * u_weights[k];
  }
  o_color = sum;
}
`;
