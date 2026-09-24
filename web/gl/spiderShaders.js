// Ray-marched spiders. Model space is the glyph's: millimetres from the spinnerets, +x toward the
// head, +y the spider's right, +z out of the web toward the viewer (her back faces the camera).

export const SPIDER_VS = `#version 300 es
uniform vec2 u_quad[4];
uniform vec2 u_viewport;
out vec2 v_p;
void main() {
  vec2 p = u_quad[gl_VertexID];
  v_p = p;
  gl_Position = vec4(p.x / u_viewport.x * 2.0 - 1.0, 1.0 - p.y / u_viewport.y * 2.0, 0.0, 1.0);
}
`;

export const SPIDER_FS = `#version 300 es
precision highp float;
precision highp int;
in vec2 v_p;
out vec4 o;

uniform vec2 u_viewport;
uniform float u_dpr;
uniform vec2 u_center;        // device px of the spinnerets
uniform vec2 u_axis;          // cos, sin of the heading
uniform float u_pxPerMm;      // device px per mm
uniform float u_zTop;         // highest point of the model (mm)
uniform vec3 u_joints[56];    // 8 legs x 7 points
uniform vec4 u_legBounds[8];  // bounding sphere per leg
uniform vec4 u_bodyBox;       // min x, max x, half width, top z of the body (mm)
uniform vec4 u_abd;           // x, rx, ry, rz
uniform vec4 u_car;           // x, rx, ry, rz
uniform vec2 u_bodyZ;         // abdomen and carapace centre heights
uniform float u_L;            // body length
uniform vec3 u_legR;          // femur, tibia, tarsus radius
uniform int u_pattern;
uniform int u_eyes;
uniform int u_bandStyle;
uniform vec3 u_colAbd;
uniform vec3 u_colCar;
uniform vec3 u_colLeg;
uniform vec3 u_colBand;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;
uniform vec3 u_colTips;
uniform vec3 u_colTissue;
uniform float u_translucency;
uniform float u_bodyVisible;
uniform float u_legFrom;
uniform float u_breath;
uniform float u_fade;
uniform float u_gloss;        // species gloss x setting
uniform float u_hair;         // species hair x setting
uniform int u_steps;
uniform float u_shadows;
uniform float u_seed;
uniform float u_spines;       // 1 when the spider is large enough on screen for leg spines

uniform sampler2D u_light;
uniform vec3 u_view;          // zoom, offset x, offset y (CSS px)
uniform vec3 u_sunDir;
uniform vec3 u_sunRadiance;
uniform vec3 u_ambient;

const float PI = 3.14159265;

float hash13(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.zyx + 31.32);
  return fract((p.x + p.y) * p.z);
}
float noise3(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float sdEllipsoid(vec3 p, vec3 r) {
  float k0 = length(p / r);
  float k1 = length(p / (r * r));
  return k0 * (k0 - 1.0) / max(k1, 1e-6);
}
float sdSphere(vec3 p, float r) { return length(p) - r; }
float sdRoundCone(vec3 p, vec3 a, vec3 b, float r1, float r2) {
  vec3 ba = b - a;
  float l2 = max(dot(ba, ba), 1e-8);
  float rr = r1 - r2;
  float a2 = l2 - rr * rr;
  float il2 = 1.0 / l2;
  vec3 pa = p - a;
  float y = dot(pa, ba);
  float z = y - l2;
  vec3 xv = pa * l2 - ba * y;
  float x2 = dot(xv, xv);
  float y2 = y * y * l2;
  float z2 = z * z * l2;
  float k = sign(rr) * rr * rr * x2;
  if (sign(z) * a2 * z2 > k) return sqrt(x2 + z2) * il2 - r2;
  if (sign(y) * a2 * y2 < k) return sqrt(x2 + y2) * il2 - r1;
  return (sqrt(x2 * a2 * il2) + y * rr) * il2 - r1;
}
float smin(float a, float b, float k) {
  float h = max(k - abs(a - b), 0.0) / k;
  return min(a, b) - h * h * k * 0.25;
}

vec3 abdCentre() { return vec3(u_abd.x, 0.0, u_bodyZ.x); }
vec3 carCentre() { return vec3(u_car.x, 0.0, u_bodyZ.y); }
vec3 abdRadii() { return u_abd.yzw * (1.0 + 0.015 * u_breath); }

// Leg segment radii: coxa, femur, patella, tibia, metatarsus, tarsus.
vec2 segRadius(int s, int leg) {
  float f = u_legR.x;
  float t = u_legR.y;
  float a = u_legR.z;
  float k = (leg % 4 == 2) ? 0.9 : 1.0;
  vec2 r;
  if (s == 0) r = vec2(f * 1.3, f * 1.12);
  else if (s == 1) r = vec2(f * 1.12, f * 0.86);
  else if (s == 2) r = vec2(f * 0.98, t * 1.12);
  else if (s == 3) r = vec2(t * 1.05, t * 0.78);
  else if (s == 4) r = vec2(t * 0.72, a * 1.25);
  else r = vec2(a * 1.12, a * 0.55);
  return r * k;
}

// Species features joined to the abdomen.
float extrasDist(vec3 p, float d, out float featured) {
  featured = 0.0;
  vec3 ac = abdCentre();
  vec3 ar = abdRadii();
  float L = u_L;
  if (u_pattern == 2) {
    // Garden orb-weaver: two rounded shoulder humps.
    for (int side = -1; side <= 1; side += 2) {
      vec3 c = ac + vec3(ar.x * 0.42, float(side) * ar.y * 0.52, ar.z * 0.42);
      float h = sdSphere(p - c, ar.y * 0.36);
      if (h < d) featured = 1.0;
      d = smin(d, h, ar.y * 0.35);
    }
  } else if (u_pattern == 4) {
    // Christmas jewel: six conical spines round the hard abdomen.
    for (int side = -1; side <= 1; side += 2) {
      float s = float(side);
      vec3 b0 = vec3(0.05 * L, s * 0.16 * L, ac.z + ar.z * 0.25);
      vec3 t0 = vec3(-0.08 * L, s * 0.33 * L, ac.z + ar.z * 0.85);
      vec3 b1 = vec3(0.30 * L, s * 0.22 * L, ac.z + ar.z * 0.3);
      vec3 t1 = vec3(0.30 * L, s * 0.43 * L, ac.z + ar.z * 0.9);
      vec3 b2 = vec3(0.47 * L, s * 0.13 * L, ac.z + ar.z * 0.3);
      vec3 t2 = vec3(0.62 * L, s * 0.29 * L, ac.z + ar.z * 0.95);
      float h = min(sdRoundCone(p, b0, t0, 0.055 * L, 0.012 * L),
                min(sdRoundCone(p, b1, t1, 0.055 * L, 0.012 * L), sdRoundCone(p, b2, t2, 0.05 * L, 0.012 * L)));
      if (h < d) featured = 1.0;
      d = smin(d, h, 0.03 * L);
    }
  } else if (u_pattern == 5) {
    // Scorpion-tailed: the abdomen runs on into a tapering tail that curls up.
    vec3 a0 = vec3(0.12 * L, 0.0, ac.z);
    vec3 a1 = vec3(-0.22 * L, -0.04 * L, ac.z + 0.08 * L);
    vec3 a2 = vec3(-0.5 * L, -0.12 * L, ac.z + 0.26 * L);
    vec3 a3 = vec3(-0.62 * L, -0.2 * L, ac.z + 0.5 * L);
    float h = min(sdRoundCone(p, a0, a1, ar.y * 0.62, 0.13 * L), min(sdRoundCone(p, a1, a2, 0.13 * L, 0.075 * L), sdRoundCone(p, a2, a3, 0.075 * L, 0.03 * L)));
    if (h < d) featured = 1.0;
    d = smin(d, h, 0.08 * L);
  } else if (u_pattern == 7) {
    // Magnificent spider: paired shoulder tubercles and smaller bumps on the round abdomen.
    // Two blunt shoulder tubercles, and a low pair behind them.
    for (int side = -1; side <= 1; side += 2) {
      float s = float(side);
      vec3 b0 = ac + vec3(ar.x * 0.38, s * ar.y * 0.45, ar.z * 0.62);
      float h = sdRoundCone(p, b0, b0 + vec3(0.04 * L, s * 0.07 * L, 0.2 * L), 0.13 * L, 0.07 * L);
      vec3 b1 = ac + vec3(-ar.x * 0.15, s * ar.y * 0.5, ar.z * 0.7);
      h = min(h, sdRoundCone(p, b1, b1 + vec3(0.0, s * 0.03 * L, 0.07 * L), 0.07 * L, 0.04 * L));
      if (h < d) featured = 1.0;
      d = smin(d, h, 0.07 * L);
    }
  }
  return d;
}

// Eight eyes on the head: the araneid square of medians with lateral pairs, a theridiid double
// row, or the net-caster's two enormous posterior median eyes.
float eyesDist(vec3 p) {
  vec3 cc = carCentre();
  float L = u_L;
  float hx = cc.x + u_car.y * 0.8;
  float zt = cc.z + u_car.w * 0.95;
  vec3 hub = vec3(hx, 0.0, zt);
  if (length(p - hub) > 0.35 * L) return 1e5;
  float d = 1e5;
  if (u_eyes == 1) {
    for (int side = -1; side <= 1; side += 2) {
      float s = float(side);
      d = min(d, sdSphere(p - vec3(hx + 0.03 * L, s * 0.062 * L, zt - 0.02 * L), 0.058 * L));
      d = min(d, sdSphere(p - vec3(hx + 0.05 * L, s * 0.02 * L, zt + 0.02 * L), 0.014 * L));
      d = min(d, sdSphere(p - vec3(hx - 0.04 * L, s * 0.1 * L, zt - 0.04 * L), 0.016 * L));
    }
  } else if (u_eyes == 2) {
    for (int side = -1; side <= 1; side += 2) {
      float s = float(side);
      d = min(d, sdSphere(p - vec3(hx + 0.03 * L, s * 0.022 * L, zt), 0.018 * L));
      d = min(d, sdSphere(p - vec3(hx + 0.02 * L, s * 0.06 * L, zt - 0.01 * L), 0.016 * L));
      d = min(d, sdSphere(p - vec3(hx - 0.02 * L, s * 0.026 * L, zt), 0.017 * L));
      d = min(d, sdSphere(p - vec3(hx - 0.025 * L, s * 0.064 * L, zt - 0.012 * L), 0.015 * L));
    }
  } else {
    for (int side = -1; side <= 1; side += 2) {
      float s = float(side);
      d = min(d, sdSphere(p - vec3(hx + 0.04 * L, s * 0.026 * L, zt), 0.021 * L));
      d = min(d, sdSphere(p - vec3(hx - 0.005 * L, s * 0.03 * L, zt + 0.004 * L), 0.019 * L));
      d = min(d, sdSphere(p - vec3(hx + 0.01 * L, s * (u_car.z * 0.62), zt - u_car.w * 0.3), 0.014 * L));
      d = min(d, sdSphere(p - vec3(hx - 0.02 * L, s * (u_car.z * 0.6), zt - u_car.w * 0.34), 0.013 * L));
    }
  }
  return d;
}

// Chelicerae and pedipalps at the front of the head.
float mouthDist(vec3 p) {
  vec3 cc = carCentre();
  float L = u_L;
  float hx = cc.x + u_car.y * 0.85;
  if (length(p - vec3(hx + 0.08 * L, 0.0, cc.z)) > 0.4 * L) return 1e5;
  float d = 1e5;
  for (int side = -1; side <= 1; side += 2) {
    float s = float(side);
    d = min(d, sdEllipsoid(p - vec3(hx + 0.06 * L, s * 0.035 * L, cc.z - 0.02 * L), vec3(0.07 * L, 0.035 * L, 0.05 * L)));
    vec3 a = vec3(hx - 0.02 * L, s * u_car.z * 0.55, cc.z - 0.01 * L);
    vec3 b = a + vec3(0.13 * L, s * 0.05 * L, 0.06 * L);
    vec3 c = b + vec3(0.1 * L, s * 0.01 * L, -0.05 * L);
    d = min(d, min(sdRoundCone(p, a, b, 0.025 * L, 0.02 * L), sdRoundCone(p, b, c, 0.02 * L, 0.028 * L)));
  }
  return d;
}

float bodyDist(vec3 p, out float featured) {
  featured = 0.0;
  if (u_bodyVisible < 0.5) return 1e5;
  vec3 ac = abdCentre();
  vec3 ar = abdRadii();
  float d = sdEllipsoid(p - ac, ar);
  if (d < 0.1 * u_L) {
    vec3 q = (p - ac) / ar;
    if (u_pattern == 1) d += 0.012 * u_L * sin(q.x * 9.0) * smoothstep(-0.2, 0.5, q.z);
    // Two pairs of sigilla, the muscle-attachment dimples on the back of the abdomen.
    float dimples = 0.0;
    for (int k = 0; k < 2; k++) {
      float xk = k == 0 ? 0.25 : -0.12;
      dimples += exp(-dot(vec2(q.x - xk, abs(q.y) - 0.22) * vec2(9.0, 11.0), vec2(q.x - xk, abs(q.y) - 0.22) * vec2(9.0, 11.0)));
    }
    d += 0.012 * u_L * dimples * smoothstep(0.3, 0.8, q.z);
  }
  d = extrasDist(p, d, featured);
  vec3 cc = carCentre();
  float dc = sdEllipsoid(p - cc, u_car.yzw);
  float dh = sdEllipsoid(p - (cc + vec3(u_car.y * 0.5, 0.0, u_car.w * 0.3)), vec3(u_car.y * 0.5, u_car.z * 0.66, u_car.w * 0.85));
  dc = smin(dc, dh, u_car.w * 0.6);
  float dp = sdRoundCone(p, ac + vec3(ar.x * 0.82, 0.0, 0.0), cc - vec3(u_car.y * 0.8, 0.0, 0.0), 0.05 * u_L, 0.045 * u_L);
  dc = smin(dc, dp, 0.03 * u_L);
  // Spinnerets at the rear.
  float ds = sdRoundCone(p, ac - vec3(ar.x * 0.85, 0.0, ar.z * 0.25), ac - vec3(ar.x * 1.05, 0.0, ar.z * 0.35), 0.06 * u_L, 0.025 * u_L);
  d = smin(d, ds, 0.02 * u_L);
  return min(d, dc);
}

// Macrosetae: short spines raked toward the tip, two per ring along the femur, tibia and metatarsus.
float spineDist(vec3 p, vec3 a, vec3 b, vec2 r, float leg, float s) {
  vec3 ba = b - a;
  float len = length(ba);
  vec3 axis = ba / max(len, 1e-5);
  float along = clamp(dot(p - a, axis), 0.0, len);
  float spacing = max(len / 5.0, r.x * 2.4);
  float k = floor(along / spacing + 0.5);
  float at = clamp(k * spacing, spacing * 0.5, len - spacing * 0.3);
  float radius = mix(r.x, r.y, at / max(len, 1e-5));
  vec3 up = normalize(vec3(0.0, 0.0, 1.0) - axis * axis.z + vec3(1e-4, 0.0, 0.0));
  vec3 side = normalize(cross(axis, up));
  float twist = fract(sin((k + leg * 7.0 + s * 13.0) * 12.9898) * 43758.5453) * 1.2 - 0.6;
  float d = 1e5;
  for (int j = -1; j <= 1; j += 2) {
    vec3 out1 = normalize(up * 0.75 + side * float(j) * (0.65 + 0.2 * twist));
    vec3 base = a + axis * at + out1 * radius * 0.8;
    vec3 tip = base + normalize(out1 + axis * 1.3) * radius * 2.6;
    d = min(d, sdRoundCone(p, base, tip, radius * 0.22, radius * 0.05));
  }
  return d;
}

float legsDist(vec3 p, float best) {
  float d = best;
  for (int leg = 0; leg < 8; leg++) {
    vec4 bound = u_legBounds[leg];
    if (length(p - bound.xyz) - bound.w > d) continue;
    for (int s = 0; s < 6; s++) {
      if (float(s) < u_legFrom) continue;
      vec2 r = segRadius(s, leg);
      vec3 a = u_joints[leg * 7 + s];
      vec3 b = u_joints[leg * 7 + s + 1];
      float seg = sdRoundCone(p, a, b, r.x, r.y);
      if (u_spines > 0.5 && (s == 1 || s == 3 || s == 4) && seg < r.x * 3.0) seg = min(seg, spineDist(p, a, b, r, float(leg), float(s)));
      d = min(d, seg);
    }
  }
  return d;
}

float map(vec3 p) {
  float featured;
  float d = bodyDist(p, featured);
  if (u_bodyVisible > 0.5) {
    d = min(d, eyesDist(p));
    d = min(d, mouthDist(p));
  }
  return legsDist(p, d);
}

// Material: x id (1 abdomen, 2 carapace, 3 leg, 4 eye, 5 mouthparts, 6 feature), y leg, z segment + t.
vec3 material(vec3 p) {
  float featured;
  float best = bodyDist(p, featured);
  vec3 cc = carCentre();
  vec3 id = vec3(0.0);
  if (best < 1e4) {
    float da = sdEllipsoid(p - abdCentre(), abdRadii());
    float dc = sdEllipsoid(p - cc, u_car.yzw);
    id = vec3(p.x > (abdCentre().x + u_abd.y * 0.95) ? 2.0 : 1.0, 0.0, 0.0);
    if (featured > 0.5 && da > 0.01 * u_L) id.x = 6.0;
    if (dc < da && p.x > abdCentre().x + u_abd.y * 0.6) id.x = 2.0;
  }
  if (u_bodyVisible > 0.5) {
    float de = eyesDist(p);
    if (de < best) { best = de; id = vec3(4.0, 0.0, 0.0); }
    float dm = mouthDist(p);
    if (dm < best) { best = dm; id = vec3(5.0, 0.0, 0.0); }
  }
  for (int leg = 0; leg < 8; leg++) {
    vec4 bound = u_legBounds[leg];
    if (length(p - bound.xyz) - bound.w > best) continue;
    for (int s = 0; s < 6; s++) {
      if (float(s) < u_legFrom) continue;
      vec3 a = u_joints[leg * 7 + s];
      vec3 b = u_joints[leg * 7 + s + 1];
      vec2 r = segRadius(s, leg);
      float d = sdRoundCone(p, a, b, r.x, r.y);
      if (d < best) {
        best = d;
        vec3 ba = b - a;
        float t = clamp(dot(p - a, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
        id = vec3(3.0, float(leg), float(s) + t);
      }
    }
  }
  return id;
}

vec3 normalAt(vec3 p) {
  float e = max(0.02 / u_pxPerMm, 0.0015 * u_L);
  const vec2 k = vec2(1.0, -1.0);
  return normalize(k.xyy * map(p + k.xyy * e) + k.yyx * map(p + k.yyx * e) + k.yxy * map(p + k.yxy * e) + k.xxx * map(p + k.xxx * e));
}

float band(float x, float centre, float halfWidth) {
  return smoothstep(halfWidth * 1.3, halfWidth * 0.7, abs(x - centre));
}

vec3 spot(vec3 colour, vec3 base, vec2 q, vec2 c, float r) {
  return mix(base, colour, smoothstep(r, r * 0.7, length(q - c)));
}

// Species colour patterns in normalised abdomen coordinates (x rear -1 .. front +1, y across).
vec3 abdomenColour(vec3 p, out float glossBoost) {
  vec3 ac = abdCentre();
  vec3 q = (p - ac) / abdRadii();
  float x = q.x;
  float y = q.y;
  float top = smoothstep(-0.35, 0.35, q.z);
  vec3 c = u_colAbd;
  float n = noise3(p / u_L * 22.0 + u_seed);
  glossBoost = 0.0;
  float L = u_L;
  vec2 g = vec2((p.x - ac.x) / abdRadii().x, p.y / abdRadii().y);
  if (u_pattern == 0) {
    // Golden orb-weaver: silvery body with cream bands and a darker dorsal field.
    c = mix(u_colAbd * 1.08, u_c3, 0.25 * n);
    c = mix(c, u_c2, 0.6 * smoothstep(0.5, 0.25, abs(y)) * smoothstep(-0.55, -0.35, x) * smoothstep(0.85, 0.6, x) * top);
    for (int k = 0; k < 3; k++) {
      float xc = k == 0 ? -0.66 : (k == 1 ? -0.1 : 0.45);
      c = mix(c, u_c1, 0.9 * band(x, xc, 0.075) * top);
    }
    glossBoost = 0.3;
  } else if (u_pattern == 1) {
    // St Andrew's Cross: silver shoulders, yellow body, thin black cross-bands, a bright yellow girdle.
    c = mix(u_colAbd, u_c3, smoothstep(0.35, 0.6, x));
    c = mix(c, u_c2, 0.85 * band(x, -0.1, 0.17) * top);
    for (int k = 0; k < 3; k++) {
      float xc = k == 0 ? -0.66 : (k == 1 ? -0.34 : 0.3);
      c = mix(c, u_c1, 0.92 * band(x + 0.06 * sin(y * 5.0), xc, 0.05) * top);
    }
    c = mix(c, u_c1 * 1.6 + vec3(0.08, 0.02, 0.0), 0.5 * smoothstep(0.75, 0.95, abs(y)) * smoothstep(-0.9, 0.2, x));
    glossBoost = 0.2;
  } else if (u_pattern == 2) {
    // Garden orb-weaver: brown with a pale median stripe, a dark scalloped folium and pale spots.
    float edge = 0.55 + 0.12 * sin(x * 14.0);
    float folium = smoothstep(edge + 0.08, edge - 0.08, abs(y)) * smoothstep(0.95, 0.3, x);
    c = mix(u_colAbd * 1.15, u_colAbd * 0.55, folium * top);
    c = mix(c, u_c3, 0.8 * smoothstep(0.12, 0.05, abs(y)) * smoothstep(-0.1, 0.4, x) * top);
    c = spot(u_c2, c, g, vec2(-0.45, -0.35), 0.12);
    c = spot(u_c2, c, g, vec2(0.0, 0.38), 0.13);
    c = spot(u_c2, c, g, vec2(0.25, -0.22), 0.1);
    c = mix(c, u_c1, smoothstep(0.62, 0.9, x) * smoothstep(0.25, 0.55, abs(y)));
    c *= 0.85 + 0.3 * n;
  } else if (u_pattern == 3) {
    // Leaf-curling spider: tan with a dark central band.
    c = mix(u_colAbd, u_c1, 0.8 * smoothstep(0.55, 0.35, abs(y)) * smoothstep(-0.8, -0.3, x) * top);
    c *= 0.9 + 0.2 * n;
  } else if (u_pattern == 4) {
    // Christmas jewel: black hard shell with white and yellow spots.
    c = u_colAbd;
    c = spot(u_c1, c, g, vec2(-0.39, -0.48), 0.2);
    c = spot(u_c1, c, g, vec2(0.21, 0.48), 0.21);
    c = spot(u_c1, c, g, vec2(0.42, -0.28), 0.14);
    c = spot(u_c1, c, g, vec2(-0.55, 0.4), 0.11);
    c = spot(u_c2, c, g, vec2(0.27, 0.0), 0.17);
    glossBoost = 0.6;
  } else if (u_pattern == 5) {
    // Scorpion-tailed: warm tan with a pale dorsal saddle.
    c = mix(u_colAbd, u_c2, 0.7 * smoothstep(0.45, 0.2, abs(y - 0.1)) * smoothstep(-0.2, 0.3, x) * top);
    c *= 0.9 + 0.2 * n;
  } else if (u_pattern == 6) {
    // Net-casting: slim brown stick with dark and pale longitudinal stripes.
    c = mix(u_colAbd, u_c1, 0.8 * smoothstep(0.3, 0.15, abs(y)));
    c = mix(c, u_c2, 0.6 * smoothstep(0.12, 0.0, abs(abs(y) - 0.55)));
    c *= 0.85 + 0.3 * n;
  } else if (u_pattern == 7) {
    // Magnificent: cream with pink and yellow spots.
    c = u_colAbd * (0.95 + 0.1 * n);
    c = spot(u_c1, c, g, vec2(-0.72, -0.35), 0.18);
    c = spot(u_c2, c, g, vec2(-0.43, 0.3), 0.22);
    c = spot(u_c1, c, g, vec2(-0.2, -0.09), 0.18);
    c = spot(u_c2, c, g, vec2(0.02, 0.45), 0.15);
    c = spot(u_c1, c, g, vec2(0.15, -0.5), 0.14);
    c = spot(u_c2, c, g, vec2(0.6, 0.23), 0.1);
  } else if (u_pattern == 8) {
    // Redback: glossy black with the red dorsal stripe.
    float w = mix(0.08, 0.17, smoothstep(-0.9, 0.3, x));
    float stripe = smoothstep(w + 0.05, w - 0.02, abs(y)) * smoothstep(-0.95, -0.8, x) * smoothstep(0.62, 0.48, x);
    c = mix(u_colAbd, u_c1 * 1.15, stripe * top);
    glossBoost = 0.8;
  }
  // The ventral side is darker.
  c *= mix(0.4, 1.0, smoothstep(-0.7, 0.1, q.z));
  return c;
}

vec3 carapaceColour(vec3 p) {
  vec3 cc = carCentre();
  vec3 q = (p - cc) / u_car.yzw;
  float a = atan(q.y, q.x - 0.1);
  float striae = 0.5 + 0.5 * cos(a * 8.0);
  vec3 c = u_colCar * (0.8 + 0.25 * striae * smoothstep(0.15, 0.7, length(q.xy)));
  c *= 0.8 + 0.25 * smoothstep(0.35, 0.0, abs(q.y)) * smoothstep(-0.8, 0.5, q.x);
  c *= mix(0.5, 1.0, smoothstep(-0.6, 0.2, q.z));
  if (u_pattern == 1 || u_pattern == 0) c = mix(c, u_c3, 0.35 * smoothstep(0.2, 0.8, q.z));
  return c;
}

vec3 legColour(float leg, float seg, vec3 p) {
  int s = int(seg);
  float t = fract(seg);
  vec3 c = u_colLeg;
  if (u_bandStyle == 1) {
    // Pale "knees": the end of the femur and the patella.
    float knee = (s == 1 && t > 0.7) || s == 2 ? 1.0 : 0.0;
    c = mix(c, u_colBand, knee);
  } else if (u_bandStyle == 2) {
    // Alternating pale and dark bands, one pair per segment.
    if (s >= 1 && s <= 4) {
      float b = smoothstep(0.38, 0.48, t) * smoothstep(0.92, 0.82, t);
      c = mix(u_colTips * 1.3, u_colBand, b);
    }
  } else if (u_bandStyle == 3) {
    c = mix(c, c * 0.45, smoothstep(0.82, 0.95, t) + smoothstep(0.12, 0.02, t) * 0.5);
  }
  // Articulations darken; tarsi fade to the tip colour.
  c *= 0.72 + 0.28 * smoothstep(0.0, 0.1, t) * smoothstep(1.0, 0.9, t);
  if (s == 5) c = mix(c, u_colTips, smoothstep(0.2, 0.9, t));
  float streak = noise3(vec3(p.x * 40.0 / u_L, p.y * 40.0 / u_L, p.z * 160.0 / u_L) + leg * 3.1);
  return c * (0.85 + 0.3 * streak);
}

float softShadow(vec3 ro, vec3 rd) {
  float res = 1.0;
  float t = 0.03 * u_L;
  for (int i = 0; i < 24; i++) {
    float h = map(ro + rd * t);
    res = min(res, 9.0 * h / t);
    t += clamp(h, 0.015 * u_L, 0.2 * u_L);
    if (res < 0.02 || t > 2.5 * u_L) break;
  }
  return clamp(res, 0.0, 1.0);
}

float occlusion(vec3 p, vec3 n) {
  float occ = 0.0;
  float w = 1.0;
  for (int i = 1; i <= 5; i++) {
    float h = 0.03 * u_L * float(i);
    occ += (h - map(p + n * h)) * w;
    w *= 0.65;
  }
  return clamp(1.0 - occ / (0.08 * u_L), 0.0, 1.0);
}

void main() {
  vec2 d = v_p - u_center;
  vec2 local = vec2(dot(d, u_axis), dot(d, vec2(-u_axis.y, u_axis.x))) / u_pxPerMm;
  float pixel = 1.0 / u_pxPerMm;
  // Footprint test: most of the quad is empty space between the legs. A ray that misses every part's
  // bounding volume is discarded at once; the rest start just above the tallest part beneath them.
  float startZ = -1e9;
  for (int leg = 0; leg < 8; leg++) {
    vec4 b = u_legBounds[leg];
    float reach = b.w + pixel;
    vec2 off = local - b.xy;
    if (dot(off, off) < reach * reach) startZ = max(startZ, b.z + sqrt(max(0.0, reach * reach - dot(off, off))));
  }
  if (u_bodyVisible > 0.5 && local.x > u_bodyBox.x && local.x < u_bodyBox.y && abs(local.y) < u_bodyBox.z) startZ = max(startZ, u_bodyBox.w);
  if (startZ < -1e8) discard;
  vec3 ro = vec3(local, min(u_zTop, startZ + pixel));
  float t = 0.0;
  float tMax = ro.z + 0.25 * u_L;
  float minD = 1e9;
  float tMin = 0.0;
  bool hit = false;
  for (int i = 0; i < 200; i++) {
    if (i >= u_steps) break;
    float h = map(ro - vec3(0.0, 0.0, t));
    if (h < minD) { minD = h; tMin = t; }
    if (h < 0.3 * pixel) { hit = true; break; }
    t += max(h * 0.92, 0.1 * pixel);
    if (t > tMax) break;
  }
  float cover = hit ? 1.0 : clamp(1.0 - minD / (0.75 * pixel), 0.0, 1.0);
  if (cover <= 0.004) discard;
  vec3 pos = ro - vec3(0.0, 0.0, hit ? t : tMin);
  vec3 n = normalAt(pos);
  vec3 id = material(pos);

  // Lighting in model space.
  vec3 S = normalize(vec3(dot(u_sunDir.xy, u_axis), dot(u_sunDir.xy, vec2(-u_axis.y, u_axis.x)), u_sunDir.z));
  vec3 V = vec3(0.0, 0.0, 1.0);
  vec2 stagePx = (v_p / u_dpr - u_view.yz) / u_view.x;
  vec2 suv = stagePx / (u_viewport / u_dpr);
  float vis = texture(u_light, vec2(suv.x, 1.0 - suv.y)).g;
  float gloss = u_gloss;
  float hair = u_hair;
  float thin = 0.0;
  vec3 albedo;
  float glossBoost = 0.0;
  if (id.x < 1.5) {
    albedo = abdomenColour(pos, glossBoost);
    thin = 0.35;
  } else if (id.x < 2.5) {
    albedo = carapaceColour(pos);
    thin = 0.15;
  } else if (id.x < 3.5) {
    albedo = legColour(id.y, id.z, pos);
    gloss *= 0.55;
    thin = 0.8;
  } else if (id.x < 4.5) {
    albedo = vec3(0.006, 0.005, 0.006);
    gloss = 2.2;
    hair = 0.0;
  } else if (id.x < 5.5) {
    albedo = u_colCar * 0.55;
    thin = 0.3;
  } else {
    float gb;
    albedo = abdomenColour(pos, gb);
    if (u_pattern == 4) albedo = mix(u_colAbd * 1.2, u_c3 * 0.45, smoothstep(0.02 * u_L, 0.1 * u_L, pos.z - u_bodyZ.x - u_abd.w * 0.5));
    if (u_pattern == 7) albedo = mix(u_c3, u_c1, 0.25);
    if (u_pattern == 5) albedo = mix(u_c1, u_c2, 0.35 * smoothstep(0.0, 0.2 * u_L, pos.z - u_bodyZ.x));
    thin = 0.5;
  }
  gloss *= 1.0 + glossBoost;
  // Fine cuticle grain perturbs the normal a little.
  if (id.x < 2.5) {
    vec3 g = vec3(noise3(pos / u_L * 90.0), noise3(pos / u_L * 90.0 + 17.0), noise3(pos / u_L * 90.0 + 31.0)) - 0.5;
    n = normalize(n + g * 0.12);
  }
  float ndl = dot(n, S);
  float wrap = max(0.0, (ndl + 0.3) / 1.3);
  // Bounce light from the sunlit surroundings: a soft key from the upper front that models form.
  vec3 keyWorld = normalize(vec3(-0.45, -0.55, 0.7));
  vec3 K = normalize(vec3(dot(keyWorld.xy, u_axis), dot(keyWorld.xy, vec2(-u_axis.y, u_axis.x)), keyWorld.z));
  vec3 keyRadiance = u_ambient * 1.25 + u_sunRadiance * 0.07;
  float keyDiffuse = max(0.0, (dot(n, K) + 0.15) / 1.15);
  vec3 HK = normalize(K + vec3(0.0, 0.0, 1.0));
  float shadow = u_shadows > 0.5 ? softShadow(pos + n * 0.02 * u_L, S) : 1.0;
  float ao = occlusion(pos, n);
  vec3 H = normalize(S + V);
  float specPow = mix(18.0, 220.0, clamp(gloss * 0.6, 0.0, 1.0));
  float nv = max(0.0, dot(n, V));
  float fresnel = 0.04 + 0.96 * pow(1.0 - nv, 5.0);
  float spec = pow(max(0.0, dot(n, H)), specPow) * (specPow + 8.0) / 30.0 * gloss * (0.25 + fresnel);
  // Fill: dimmer from the camera side, brighter from the open sky behind the web.
  vec3 amb = u_ambient * mix(0.45, 1.1, 0.5 - 0.5 * n.z) * ao;
  vec3 sun = u_sunRadiance * vis * shadow;
  vec3 col = albedo * (amb + sun * wrap + keyRadiance * keyDiffuse * ao);
  col += sun * spec;
  float keySpec = pow(max(0.0, dot(n, HK)), specPow) * (specPow + 8.0) / 30.0 * gloss * (0.25 + fresnel);
  col += keyRadiance * keySpec * ao;
  // Glossy cuticle mirrors the bright sky behind the web at grazing angles.
  vec3 R = reflect(vec3(0.0, 0.0, -1.0), n);
  float skyward = smoothstep(-0.2, 0.6, -R.z);
  col += (u_ambient * 1.5 + u_sunRadiance * 0.15) * skyward * fresnel * gloss * 0.6 * ao;
  // Light passing through thin legs and the abdomen's rim when backlit.
  float back = max(0.0, -S.z);
  float depthIn = -map(pos - n * 0.12 * u_L) / (0.12 * u_L);
  float transmit = clamp(1.0 - depthIn, 0.0, 1.0) * thin;
  // Pigmented leg cuticle filters what comes through: dark legs stay dark against the sun while
  // pale joints and bands glow.
  vec3 through = u_colTissue;
  if (id.x > 2.5 && id.x < 3.5) through = sqrt(u_colTissue * albedo) * smoothstep(0.02, 0.35, dot(albedo, vec3(0.2126, 0.7152, 0.0722)));
  col += through * u_sunRadiance * vis * back * transmit * (0.35 + 0.65 * pow(1.0 - nv, 2.0)) * 0.6 * u_translucency;
  // Setae catch the light at grazing angles.
  float rim = pow(1.0 - nv, 3.0);
  vec2 facing = n.xy / max(length(n.xy), 1e-4);
  vec2 toSun = S.xy / max(length(S.xy), 1e-4);
  col += hair * rim * (amb * 0.5 + u_sunRadiance * vis * 0.6 * max(0.0, dot(facing, toSun)) * (0.4 + back)) * mix(albedo, vec3(1.0), 0.5);
  if (id.x > 3.5 && id.x < 4.5) {
    // A tiny catchlight of the bright sky in each eye.
    col += (u_ambient * 3.0 + u_sunRadiance * 0.2) * smoothstep(0.985, 0.997, dot(n, normalize(vec3(-S.xy * 0.5 + vec2(-0.2, -0.3), 1.0))));
  }
  float a = cover * u_fade;
  o = vec4(col * a, a);
}
`;
