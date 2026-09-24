"""Browser verification for the Spun, not drawn viewer (brief §11.3).

Starts tools/serve.py on a free port, drives Chromium through Playwright and writes
web/verification/report.json, the cited screenshots and web/verification/README.md.
Exits non-zero when any check fails.
"""
from __future__ import annotations

import io
import json
import math
import shutil
import socket
import struct
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "verification"
BUDGET_BYTES = 400 * 1024
BG = (5, 6, 12)
NEVER = 0xFFFFFFFF
KIND_AUX = 6
FLAG_ENV, FLAG_INVISIBLE = 2, 4
BEAD_GLUE = 2
SHELL_PATHS = {"/", "/index.html", "/style.css", "/app.js", "/silk.js", "/core/stage.js", "/core/instances.js",
               "/core/render2d.js", "/core/overlay.js", "/core/ui.js", "/gl/glRenderer.js", "/gl/shaders.js",
               "/manifest.webmanifest", "/icons/favicon.svg", "/icons/apple-touch-icon.png"}
SWIFTSHADER_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

try:
    import numpy as np
    from PIL import Image
    from playwright.sync_api import sync_playwright
except ImportError as error:  # pragma: no cover - environment guard
    print(f"verify_web.py needs playwright, numpy and pillow ({error}).\n"
          "Install with: pip install playwright numpy pillow && python -m playwright install chromium", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- data helpers

def decode_silk(path: Path) -> dict:
    raw = path.read_bytes()
    header = struct.unpack_from("<4sHHHHIIHHHBBB3x", raw, 0)
    count, bead_count, coord_scale, width_scale = header[5], header[6], header[9], header[10]
    records = []
    for i in range(count):
        x0, y0, x1, y1, death, kind, width, r, g, b, lod, flags, alpha = struct.unpack_from("<4HI8B", raw, 32 + i * 20)
        records.append({"i": i, "p0": (x0 / coord_scale, y0 / coord_scale), "p1": (x1 / coord_scale, y1 / coord_scale),
                        "death": death, "kind": kind, "width": width / width_scale, "lod": lod, "flags": flags, "alpha": alpha})
    beads = []
    offset = 32 + count * 20
    for j in range(bead_count):
        host, t, radius, flags = struct.unpack_from("<IHBB", raw, offset + j * 8)
        rec = records[host]
        f = t / 65535
        beads.append({"j": j, "host": host, "r": radius / 16, "flags": flags,
                      "x": rec["p0"][0] + (rec["p1"][0] - rec["p0"][0]) * f, "y": rec["p0"][1] + (rec["p1"][1] - rec["p0"][1]) * f})
    return {"count": count, "beads": beads, "records": records}


def time_for_cursor(spec: dict, target: float) -> float:
    timeline = spec["timeline"]
    for i in range(len(timeline) - 1):
        if timeline[i] <= target <= timeline[i + 1]:
            span = timeline[i + 1] - timeline[i]
            fraction = 0.0 if span == 0 else (target - timeline[i]) / span
            return (i + fraction) / (len(timeline) - 1) * spec["durationSeconds"]
    return spec["durationSeconds"]


def stage_range(spec: dict, label: str):
    stages = spec["stages"]
    for k, stage in enumerate(stages):
        if stage["label"] == label:
            end = stages[k + 1]["start"] if k + 1 < len(stages) else spec["segments"]
            return stage["start"], end
    return None


def seg_distance(p, a, b) -> float:
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    h = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - ax - dx * h, py - ay - dy * h)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------- image helpers

def shot(page) -> "np.ndarray":
    page.add_style_tag(content="#stage-hint{display:none!important}")
    return np.asarray(Image.open(io.BytesIO(page.locator("#stage").screenshot())).convert("RGB")).astype(np.int16)


def save(img, name: str, evidence: list) -> None:
    Image.fromarray(img.astype(np.uint8)).save(OUT / name)
    evidence.append(name)


def mad(a, b) -> dict:
    bg = np.array(BG, dtype=np.int16)
    mask = (np.abs(a - bg).max(axis=2) > 8) | (np.abs(b - bg).max(axis=2) > 8)
    diff = np.abs(a - b)[mask]
    return {"mad": round(float(diff.mean()), 3) if diff.size else 0.0, "pixels": int(mask.sum())}


def probe(img, x: float, y: float, radius: int = 1) -> int:
    xi, yi = int(round(x)), int(round(y))
    patch = img[max(0, yi - radius):yi + radius + 1, max(0, xi - radius):xi + radius + 1]
    return int(np.abs(patch - np.array(BG, dtype=np.int16)).max()) if patch.size else -1


# ---------------------------------------------------------------- harness

class Harness:
    def __init__(self, playwright, base: str, index: dict):
        self.p = playwright
        self.base = base
        self.index = index
        self.specs = {s["id"]: s for s in index["specimens"]}
        self.default = index["defaultSpecimen"]
        self.env: dict = {}
        self.browser = None
        self.flags: list = []

    def launch(self):
        errors = []
        for channel in (None, "chrome", "msedge"):
            try:
                browser = self.p.chromium.launch(headless=True, channel=channel, args=self.flags)
                self.env["channel"] = channel or "chromium (playwright)"
                return browser
            except Exception as error:  # noqa: BLE001 - try the next channel
                errors.append(f"{channel or 'chromium'}: {str(error).splitlines()[0]}")
        raise RuntimeError("; ".join(errors))

    def start(self):
        self.browser = self.launch()
        renderer = self.gl_renderer()
        if not renderer:
            self.browser.close()
            self.flags = SWIFTSHADER_FLAGS
            self.browser = self.launch()
            renderer = self.gl_renderer()
        self.env.update({"browserVersion": self.browser.version, "launchFlags": list(self.flags), "glRenderer": renderer,
                         "webgl2": bool(renderer), "headless": True})
        lowered = (renderer or "").lower()
        self.env["softwareRenderer"] = any(word in lowered for word in ("swiftshader", "software", "llvmpipe"))

    def gl_renderer(self):
        ctx, page, _ = self.context()
        try:
            return page.evaluate("window.__spun.stats().glRenderer")
        finally:
            ctx.close()

    def context(self, url_query: str = "debug=1&nosw=1", **options):
        options.setdefault("viewport", {"width": 1280, "height": 800})
        options.setdefault("device_scale_factor", 1)
        ctx = self.browser.new_context(**options)
        page = ctx.new_page()
        log = {"errors": [], "failed": [], "bad": [], "requests": []}
        page.on("console", lambda m: log["errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: log["errors"].append(str(e)))
        page.on("requestfailed", lambda r: log["failed"].append(r.url))
        page.on("response", lambda r: log["bad"].append(f"{r.status} {r.url}") if r.status >= 400 else None)
        page.on("request", lambda r: log["requests"].append(r.url))
        self.open(page, url_query)
        return ctx, page, log

    def open(self, page, url_query: str):
        page.goto(f"{self.base}/?{url_query}", wait_until="load")
        page.wait_for_function("window.__spun && window.__spun.ready", timeout=30000)
        page.evaluate("async () => await window.__spun.ready")

    # page helpers -----------------------------------------------------
    @staticmethod
    def stats(page):
        return page.evaluate("window.__spun.stats()")

    @staticmethod
    def settle(page, timeout=60000):
        page.wait_for_function("!window.__spun.stats().rafActive", timeout=timeout)
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    @staticmethod
    def plant(page, sid, x=640, y=357):
        page.evaluate("([id, x, y]) => window.__spun.plant(id, x, y)", [sid, x, y])

    @staticmethod
    def seek(page, seconds):
        page.evaluate("s => window.__spun.seek(s)", seconds)

    def origin(self, page, sid, k=0):
        pl = self.stats(page)["placements"][k]
        spec = self.specs[sid]
        return pl["anchorX"] - spec["anchor"]["x"] * pl["scale"], pl["anchorY"] - spec["anchor"]["y"] * pl["scale"], pl["scale"]

    def backends(self):
        return ["2d", "gl"] if self.env.get("webgl2") else ["2d"]


# ---------------------------------------------------------------- checks

def check_cold_load(h: Harness):
    ctx, page, log = h.context()
    try:
        spec = h.specs[h.default]
        allowed = SHELL_PATHS | {"/specimens/index.json", f"/specimens/{spec['file']}"}
        paths = sorted({urllib.parse.urlparse(u).path for u in log["requests"]})
        unexpected = [p for p in paths if p not in allowed]
        index_bytes = (WEB / "specimens" / "index.json").stat().st_size
        silk_bytes = (WEB / "specimens" / spec["file"]).stat().st_size
        numbers = {"consoleErrors": log["errors"], "failedRequests": sorted(log["failed"]), "httpErrors": sorted(log["bad"]),
                   "fetched": paths, "unexpected": unexpected, "indexBytes": index_bytes, "defaultSilkBytes": silk_bytes,
                   "budgetBytes": BUDGET_BYTES}
        ok = not log["errors"] and not log["failed"] and not log["bad"] and not unexpected and index_bytes + silk_bytes <= BUDGET_BYTES
        return ok, numbers, []
    finally:
        ctx.close()


def check_all_species(h: Harness):
    ctx, page, log = h.context()
    try:
        rows = {}
        ok = True
        for backend in h.backends():
            page.evaluate(f"window.__spun.setBackend('{backend}')")
            for sid, spec in h.specs.items():
                page.evaluate("window.__spun.clear()")
                h.plant(page, sid)
                page.wait_for_function("window.__spun.stats().instances === 1")
                h.seek(page, "end")
                h.settle(page)
                s = h.stats(page)
                decoded = page.evaluate("id => window.__spun.decoded(id)", sid)
                good = decoded == {"segments": spec["segments"], "beads": spec["beads"]} and s["cursors"][0]["cursor"] == spec["segments"]
                ok &= good
                rows[f"{backend}:{sid}"] = {"decoded": decoded, "cursor": s["cursors"][0]["cursor"], "ok": good}
        ok &= not log["errors"]
        return ok, {"species": rows, "backends": h.backends(), "consoleErrors": log["errors"]}, []
    finally:
        ctx.close()


def check_parity(h: Harness):
    if not h.env.get("webgl2"):
        return None, {"reason": "WebGL2 unavailable"}, []
    snare = next((s["id"] for s in h.index["specimens"] if s["kind"] == "snare"), None)
    orb = next((s["id"] for s in h.index["specimens"] if s["kind"] == "orb" and s["id"] != h.default), None)
    chosen = [sid for sid in (h.default, orb, snare) if sid]
    ctx, page, log = h.context()
    evidence, numbers, ok = [], {}, True
    try:
        for sid in chosen:
            spec = h.specs[sid]
            page.evaluate("window.__spun.clear()")
            h.plant(page, sid)
            page.wait_for_function("window.__spun.stats().instances === 1")
            for label, seconds in (("40pct", spec["durationSeconds"] * 0.4), ("end", "end")):
                h.seek(page, seconds)
                for glow in (False, True):
                    page.evaluate(f"window.__spun.setGlow({str(glow).lower()})")
                    imgs = {}
                    for backend in ("gl", "2d"):
                        page.evaluate(f"window.__spun.setBackend('{backend}')")
                        h.settle(page)
                        imgs[backend] = shot(page)
                    m = mad(imgs["gl"], imgs["2d"])
                    limit = 14 if glow else 12
                    m["limit"] = limit
                    ok &= m["mad"] <= limit
                    numbers[f"{sid}:{label}:glow{'On' if glow else 'Off'}"] = m
                    if sid == h.default and label == "end" and glow:
                        save(imgs["gl"], "parity-default-end-gl.png", evidence)
                        save(imgs["2d"], "parity-default-end-2d.png", evidence)
        page.evaluate("window.__spun.setGlow(true)")
        ok &= not log["errors"]
        numbers["consoleErrors"] = log["errors"]
        return ok, numbers, evidence
    finally:
        ctx.close()


def check_zero_uploads(h: Harness):
    if not h.env.get("webgl2"):
        return None, {"reason": "WebGL2 unavailable"}, []
    ctx, page, log = h.context()
    try:
        page.evaluate("window.__spun.setBackend('gl')")
        h.plant(page, h.default)
        page.wait_for_function("window.__spun.stats().instances === 1")
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        samples = page.evaluate("""id => new Promise(resolve => {
          const out = [];
          const tick = () => {
            const s = window.__spun.stats();
            out.push([s.glBufferUploadsLastFrame, s.rafActive]);
            if (out.length % 40 === 0) window.__spun.plant(id, 200 + out.length * 5, 357);
            if (out.length < 120) requestAnimationFrame(tick); else resolve(out);
          };
          requestAnimationFrame(tick);
        })""", h.default)
        numbers = {"frames": len(samples), "maxUploadsPerFrame": max(s[0] for s in samples),
                   "framesGrowing": sum(1 for s in samples if s[1]), "uploadsTotal": h.stats(page)["glBufferUploadsTotal"]}
        return numbers["maxUploadsPerFrame"] == 0 and numbers["framesGrowing"] == 120 and not log["errors"], numbers, []
    finally:
        ctx.close()


def check_settle(h: Harness):
    ctx, page, log = h.context()
    try:
        numbers = {}
        ok = True
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
            h.plant(page, h.default)
            page.wait_for_function("window.__spun.stats().instances === 1 && window.__spun.stats().cursors[0].cursor >= "
                                   f"{h.specs[h.default]['segments']}", timeout=120000)
            time.sleep(1.0)
            a = h.stats(page)
            time.sleep(0.5)
            b = h.stats(page)
            good = not a["rafActive"] and not b["rafActive"] and a["framesRendered"] == b["framesRendered"]
            ok &= good
            numbers[backend] = {"rafActive": b["rafActive"], "framesAt1s": a["framesRendered"], "framesAt1_5s": b["framesRendered"]}
        return ok and not log["errors"], numbers, []
    finally:
        ctx.close()


def pick_probe(record, others, scale, avoid, min_gap_px=4.0, avoid_px=30.0):
    """Point on `record` far from other drawn records and from `avoid` points (native coords)."""
    best = None
    for k in range(1, 20):
        f = k / 20
        p = (record["p0"][0] + (record["p1"][0] - record["p0"][0]) * f, record["p0"][1] + (record["p1"][1] - record["p0"][1]) * f)
        gap = min((seg_distance(p, o["p0"], o["p1"]) for o in others), default=1e9) * scale
        far = min((math.dist(p, a) for a in avoid), default=1e9) * scale
        if gap >= min_gap_px and far >= avoid_px and (best is None or gap > best[1]):
            best = (p, gap)
    return best


def fade_alpha(record, cursor, spec, count):
    """§9.3 death fade at `cursor` (1 before death)."""
    death = record["death"]
    if death == NEVER or cursor < death:
        return 1.0
    span = max(1, min(spec.get("fadeRecords", 6), count - death))
    return max(0.0, min(1.0, 1 - (cursor - death) / span))


def drawn_at_end(data):
    return [r for r in data["records"] if not r["flags"] & FLAG_INVISIBLE and r["death"] == NEVER]


def check_eating(h: Harness):
    numbers, evidence, ok = {}, [], True
    argiope = h.specs.get("st-andrews-cross")
    golden = h.specs.get("golden-orb-weaver")
    if not argiope or not golden:
        return None, {"reason": "argiope or golden missing from index.json"}, []
    ctx, page, log = h.context()
    try:
        page.evaluate("window.__spun.setGlow(false)")
        # Argiope: a dying AUX record visible mid-capture, gone at the end.
        data = decode_silk(WEB / "specimens" / argiope["file"])
        capture = stage_range(argiope, "capture spiral") or (0, argiope["segments"])
        mid = (capture[0] + capture[1]) / 2
        rests = [(s["rest"]["x"], s["rest"]["y"]) for s in argiope.get("spiders", [])]
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
            h.plant(page, "st-andrews-cross")
            page.wait_for_function("window.__spun.stats().instances === 1")
            ox, oy, scale = h.origin(page, "st-andrews-cross")
            candidates = [r for r in data["records"] if r["kind"] == KIND_AUX and r["death"] != NEVER
                          and not r["flags"] & FLAG_INVISIBLE and r["i"] < mid
                          and fade_alpha(r, mid, argiope, data["count"]) >= 0.3]
            tip = data["records"][min(int(mid), data["count"] - 1)]["p1"]
            chosen = None
            for r in sorted(candidates, key=lambda r: -math.dist(r["p0"], r["p1"])):
                others = [o for o in data["records"] if o["i"] != r["i"] and not o["flags"] & FLAG_INVISIBLE and o["i"] < mid]
                pick = pick_probe(r, others, scale, rests + [tip])
                if pick:
                    chosen = (r, pick)
                    break
            if not chosen:
                ok = False
                numbers[f"argiope:{backend}"] = {"reason": "no dying AUX record with an isolated probe point mid-capture"}
                continue
            r, (p, gap) = chosen
            sx, sy = ox + p[0] * scale, oy + p[1] * scale
            h.seek(page, time_for_cursor(argiope, mid)); h.settle(page)
            img_mid = shot(page)
            h.seek(page, "end"); h.settle(page)
            img_end = shot(page)
            v_mid, v_end = probe(img_mid, sx, sy), probe(img_end, sx, sy)
            good = v_mid > 12 and v_end <= 6
            ok &= good
            numbers[f"argiope:{backend}"] = {"record": r["i"], "death": r["death"], "cursor": round(mid, 3), "fadeAlphaMid": round(fade_alpha(r, mid, argiope, data["count"]), 3), "probe": [round(sx, 1), round(sy, 1)],
                                            "clearancePx": round(gap, 2), "deltaMid": v_mid, "deltaEnd": v_end}
            if backend == "2d":
                save(img_mid, "eating-argiope-mid.png", evidence)
                save(img_end, "eating-argiope-end.png", evidence)
        # Golden: a never-dying AUX record still drawn at the end.
        data = decode_silk(WEB / "specimens" / golden["file"])
        rests = [(s["rest"]["x"], s["rest"]["y"]) for s in golden.get("spiders", [])]
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
            h.plant(page, "golden-orb-weaver")
            page.wait_for_function("window.__spun.stats().instances === 1")
            h.seek(page, "end"); h.settle(page)
            ox, oy, scale = h.origin(page, "golden-orb-weaver")
            final = drawn_at_end(data)
            chosen = None
            for r in sorted((r for r in final if r["kind"] == KIND_AUX), key=lambda r: -math.dist(r["p0"], r["p1"])):
                pick = pick_probe(r, [o for o in final if o["i"] != r["i"]], scale, rests)
                if pick:
                    chosen = (r, pick)
                    break
            if not chosen:
                ok = False
                numbers[f"golden:{backend}"] = {"reason": "no never-dying AUX record with an isolated probe point"}
                continue
            r, (p, gap) = chosen
            sx, sy = ox + p[0] * scale, oy + p[1] * scale
            img = shot(page)
            value = probe(img, sx, sy)
            ok &= value > 12
            numbers[f"golden:{backend}"] = {"record": r["i"], "probe": [round(sx, 1), round(sy, 1)], "clearancePx": round(gap, 2), "deltaEnd": value}
            if backend == "2d":
                save(img, "eating-golden-end.png", evidence)
        page.evaluate("window.__spun.setGlow(true)")
        return ok and not log["errors"], numbers, evidence
    finally:
        ctx.close()


def check_dew(h: Harness):
    numbers, evidence, ok = {}, [], True
    ctx, page, log = h.context()
    try:
        dew_species = max(h.specs, key=lambda sid: sum(1 for b in decode_silk(WEB / "specimens" / h.specs[sid]["file"])["beads"] if not b["flags"] & BEAD_GLUE))
        spec = h.specs[dew_species]
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}'); window.__spun.setMode('dawn')")
            h.plant(page, dew_species)
            series = page.evaluate("""n => new Promise(resolve => {
              const out = [];
              const tick = () => {
                const s = window.__spun.stats();
                if (s.instances) out.push([s.cursors[0].cursor >= n, s.dewVisible]);
                if (s.rafActive || out.length < 3) requestAnimationFrame(tick); else resolve(out);
              };
              requestAnimationFrame(tick);
            })""", spec["segments"])
            growing = [d for complete, d in series if not complete]
            after = [d for complete, d in series if complete]
            good = bool(growing) and max(growing) == 0 and bool(after) and after[-1] > 0
            ok &= good
            numbers[f"dawn:{backend}"] = {"species": dew_species, "framesGrowing": len(growing), "maxDewWhileGrowing": max(growing, default=None),
                                          "framesAfterCompletion": len(after), "finalDew": after[-1] if after else None}
            if backend == "2d":
                save(shot(page), "dew-dawn.png", evidence)
        page.evaluate("window.__spun.setMode('dusk'); window.__spun.setGlow(false)")
        for sid in ("redback-spider", "magnificent-spider"):
            spec = h.specs.get(sid)
            if not spec:
                ok = False
                numbers[f"glue:{sid}"] = {"reason": "missing from index.json"}
                continue
            data = decode_silk(WEB / "specimens" / spec["file"])
            glue = [b for b in data["beads"] if b["flags"] & BEAD_GLUE]
            rests = [(s["rest"]["x"], s["rest"]["y"]) for s in spec.get("spiders", [])]
            for backend in h.backends():
                page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
                h.plant(page, sid)
                page.wait_for_function("window.__spun.stats().instances === 1")
                h.seek(page, "end"); h.settle(page)
                if not glue:
                    ok = False
                    numbers[f"glue:{sid}:{backend}"] = {"reason": "no GLUE beads in the specimen"}
                    continue
                ox, oy, scale = h.origin(page, sid)
                bead = max(glue, key=lambda b: min((math.dist((b["x"], b["y"]), r) for r in rests), default=0))
                sx, sy = ox + bead["x"] * scale, oy + bead["y"] * scale
                img = shot(page)
                value = probe(img, sx, sy, radius=max(1, int(bead["r"] * scale * 0.8)))
                ok &= value > 20
                numbers[f"glue:{sid}:{backend}"] = {"bead": bead["j"], "radiusPx": round(bead["r"] * scale, 2), "probe": [round(sx, 1), round(sy, 1)], "delta": value}
                if backend == "2d":
                    save(img, f"glue-{sid}.png", evidence)
        page.evaluate("window.__spun.setGlow(true)")
        return ok and not log["errors"], numbers, evidence
    finally:
        ctx.close()


def check_cap_fit(h: Harness):
    ctx, page, log = h.context()
    try:
        page.evaluate("id => Promise.all(Array.from({length: 13}, (_, i) => window.__spun.plant(id, 60 + i * 80, 100 + i * 40)))", h.default)
        live = h.stats(page)["instances"]
        page.evaluate("window.__spun.clear()")
        stage = page.evaluate("(() => { const r = document.querySelector('#stage').getBoundingClientRect(); return {w: r.width, h: r.height}; })()")
        for x, y in ((0, 0), (stage["w"], 0), (0, stage["h"]), (stage["w"], stage["h"])):
            h.plant(page, h.default, x, y)
        page.wait_for_function("window.__spun.stats().instances === 4")
        h.seek(page, "end"); h.settle(page)
        insets = []
        for pl in h.stats(page)["placements"]:
            b = pl["bounds"]
            insets.append(round(min(b["left"], b["top"], stage["w"] - b["left"] - b["width"], stage["h"] - b["top"] - b["height"]), 3))
        evidence = []
        save(shot(page), "corners.png", evidence)
        ok = live == 12 and min(insets) >= 4 - 1e-6 and not log["errors"]
        return ok, {"planted": 13, "live": live, "cornerInsets": insets}, evidence
    finally:
        ctx.close()


def check_reduced_motion(h: Harness):
    ctx, page, log = h.context(reduced_motion="reduce")
    try:
        numbers, ok = {}, True
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
            h.plant(page, h.default)
            page.wait_for_function("window.__spun.stats().instances === 1")
            page.evaluate("() => new Promise(r => requestAnimationFrame(r))")
            s = h.stats(page)
            cursor = s["cursors"][0]["cursor"]
            ok &= cursor == h.specs[h.default]["segments"]
            numbers[backend] = {"cursor": cursor, "segments": h.specs[h.default]["segments"]}
        return ok and not log["errors"], numbers, []
    finally:
        ctx.close()


def check_fallback(h: Harness):
    ctx, page, log = h.context("debug=1&nosw=1&nogl=1")
    try:
        h.plant(page, h.default)
        page.wait_for_function("window.__spun.stats().instances === 1")
        h.seek(page, "end"); h.settle(page)
        nogl = {"backend": h.stats(page)["backend"], "glDisabled": page.evaluate("document.querySelector('[data-value=gl]').disabled"),
                "consoleErrors": list(log["errors"])}
    finally:
        ctx.close()
    numbers = {"nogl": nogl}
    ok = nogl["backend"] == "2d" and nogl["glDisabled"] and not nogl["consoleErrors"]
    ctx, page, log = h.context()
    try:
        persisted = {}
        for backend in h.backends():
            page.evaluate(f"window.__spun.setBackend('{backend}')")
            h.open(page, "debug=1&nosw=1")
            persisted[backend] = h.stats(page)["backend"]
        numbers["persistedAfterReload"] = persisted
        ok &= all(k == v for k, v in persisted.items()) and not log["errors"]
        return ok, numbers, []
    finally:
        ctx.close()


def check_context_loss(h: Harness):
    if not h.env.get("webgl2"):
        return None, {"reason": "WebGL2 unavailable"}, []
    ctx, page, log = h.context()
    try:
        page.evaluate("window.__spun.setBackend('gl')")
        h.plant(page, h.default)
        page.wait_for_function("window.__spun.stats().instances === 1")
        h.seek(page, "end"); h.settle(page)
        before = shot(page)
        page.evaluate("""() => new Promise(resolve => {
          const gl = window.__spun.glContext();
          const ext = gl.getExtension('WEBGL_lose_context');
          gl.canvas.addEventListener('webglcontextlost', () => setTimeout(() => ext.restoreContext(), 50), { once: true });
          gl.canvas.addEventListener('webglcontextrestored', () => setTimeout(resolve, 50), { once: true });
          ext.loseContext();
        })""")
        h.settle(page)
        after = shot(page)
        evidence = []
        save(before, "context-before.png", evidence)
        save(after, "context-after.png", evidence)
        diff = int(np.abs(before - after).max())
        return diff == 0 and not log["errors"], {"maxPixelDiff": diff}, evidence
    finally:
        ctx.close()


def check_sw_install(h: Harness):
    ctx, page, log = h.context("debug=1")
    try:
        spec = h.specs[h.default]
        state = page.evaluate("""() => new Promise(resolve => {
          const deadline = Date.now() + 15000;
          const poll = async () => {
            const reg = await navigator.serviceWorker.getRegistration();
            const worker = reg && (reg.active || reg.waiting || reg.installing);
            const s = reg?.active?.state || worker?.state || (reg ? 'registered' : 'none');
            if (s === 'activated' || Date.now() > deadline || (reg && !worker)) resolve(s === 'registered' && reg && !worker ? 'redundant' : s);
            else setTimeout(poll, 200);
          };
          poll();
        })""")
        cached = page.evaluate("""async () => { const out = []; for (const k of (await caches.keys()).sort())
          for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname); return out.sort(); }""")
        need = ["/specimens/index.json", f"/specimens/{spec['file']}"]
        missing = [p for p in need if p not in cached]
        numbers = {"state": state, "precachedEntries": len(cached), "missing": missing, "httpErrors": sorted(log["bad"]),
                   "consoleErrors": log["errors"]}
        return state == "activated" and not missing, numbers, []
    finally:
        ctx.close()


def check_offline(h: Harness):
    ctx, page, log = h.context("debug=1")
    try:
        other = next((sid for sid in h.specs if sid != h.default), h.default)
        try:
            page.evaluate("() => Promise.race([navigator.serviceWorker.ready, new Promise((_, no) => setTimeout(() => no(new Error('service worker did not activate')), 15000))])")
            page.reload(); page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
            page.evaluate("async () => await window.__spun.ready")
        except Exception as error:  # noqa: BLE001
            return False, {"reason": f"service worker did not take control: {str(error).splitlines()[0]}", "httpErrors": sorted(log["bad"])}, []
        page.evaluate("id => window.__spun.plant(id, 640, 357)", other)
        ctx.set_offline(True)
        h.open(page, "debug=1")
        planted = {}
        for sid in dict.fromkeys((h.default, other)):
            page.evaluate("window.__spun.clear()")
            page.evaluate("async id => { await window.__spun.plant(id, 640, 357); window.__spun.seek('end'); }", sid)
            h.settle(page)
            planted[sid] = h.stats(page)["instances"]
        evidence = []
        save(shot(page), "offline-reload.png", evidence)
        ok = all(v == 1 for v in planted.values()) and not log["errors"]
        return ok, {"offlinePlants": planted, "consoleErrors": log["errors"]}, evidence
    finally:
        ctx.close()


def check_mobile(h: Harness):
    ctx, page, log = h.context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    try:
        dims = page.evaluate("""() => {
          const strip = document.querySelector('.species-area');
          const before = strip.scrollLeft; strip.scrollLeft = 1e6; const after = strip.scrollLeft;
          return { documentWidth: document.documentElement.scrollWidth, viewport: innerWidth, stripClient: strip.clientWidth, stripScroll: strip.scrollWidth, before, after };
        }""")
        evidence = []
        page.screenshot(path=str(OUT / "mobile-390.png")); evidence.append("mobile-390.png")
        ok = dims["documentWidth"] <= dims["viewport"] and dims["after"] > dims["before"] and not log["errors"]
        return ok, dims, evidence
    finally:
        ctx.close()


def check_keyboard(h: Harness):
    ctx, page, log = h.context()
    try:
        focused = None
        for _ in range(12):
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement?.dataset?.specimen || null")
            if focused:
                break
        page.keyboard.press("ArrowRight")
        switched = page.evaluate("document.activeElement?.dataset?.specimen || null")
        checked = page.evaluate("document.querySelector('.chip[aria-checked=true]')?.dataset.specimen")
        reached_canvas = False
        for _ in range(20):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement?.id") == "web-canvas":
                reached_canvas = True
                break
        page.keyboard.press("Enter")
        page.wait_for_function("window.__spun.stats().instances === 1", timeout=5000)
        planted_id = h.stats(page)["cursors"][0]["id"]
        page.keyboard.press("Escape")
        cleared = h.stats(page)["instances"] == 0
        numbers = {"firstChip": focused, "afterArrow": switched, "checked": checked, "reachedStage": reached_canvas,
                   "plantedWithEnter": planted_id, "escapeCleared": cleared}
        ok = bool(focused) and switched != focused and checked == switched and reached_canvas and planted_id == switched and cleared
        return ok and not log["errors"], numbers, []
    finally:
        ctx.close()


def check_performance(h: Harness):
    ctx, page, log = h.context()
    try:
        numbers = {"glRenderer": h.env.get("glRenderer"), "softwareRenderer": h.env.get("softwareRenderer")}
        for backend in h.backends():
            page.evaluate(f"window.__spun.clear(); window.__spun.setBackend('{backend}')")
            page.evaluate("id => Promise.all(Array.from({length: 12}, (_, i) => window.__spun.plant(id, 110 + (i % 6) * 210, 200 + Math.floor(i / 6) * 330)))", h.default)
            times = page.evaluate("""() => new Promise(resolve => {
              const out = []; let last = null;
              const tick = t => {
                if (last !== null) out.push(t - last);
                last = t;
                if (window.__spun.stats().rafActive && out.length < 240) requestAnimationFrame(tick); else resolve(out);
              };
              requestAnimationFrame(tick);
            })""")
            ordered = sorted(times)
            numbers[backend] = {"frames": len(times), "meanMs": round(sum(times) / len(times), 2) if times else None,
                                "p95Ms": round(ordered[int(0.95 * (len(ordered) - 1))], 2) if times else None}
        numbers["note"] = ("software renderer: these timings are not representative of GPU hardware; no 60 fps claim"
                           if h.env.get("softwareRenderer") else "hardware GPU as named in glRenderer")
        ok = all(numbers[b]["frames"] > 0 for b in h.backends()) and not log["errors"]
        return ok, numbers, []
    finally:
        ctx.close()


CONTRAST_JS = """() => {
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return [0, 0, 0, 0];
    const v = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const over = (top, under) => { const a = top[3] + under[3] * (1 - top[3]);
    return a === 0 ? [0, 0, 0, 0] : [0, 1, 2].map(i => (top[i] * top[3] + under[i] * under[3] * (1 - top[3])) / a).concat([a]); };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const background = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor);
      if (c[3] > 0) layers.push(c); if (c[3] >= 1) break; }
    let bg = [5, 6, 12, 1]; for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg); return bg; };
  const selector = el => el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    if (el.closest('.sr-only, [hidden]') || el.closest('button:disabled')) continue;
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden' || cs.display === 'none') continue;
    let op = 1; for (let n = el; n; n = n.parentElement) op *= Number(getComputedStyle(n).opacity);
    if (op < 0.05) continue;
    const bg = background(el); const fg = over(parse(cs.color), bg);
    const a = lum(fg), b = lum(bg); const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    out.push({ selector: selector(el), text: el.textContent.trim().slice(0, 30), ratio: Math.round(ratio * 100) / 100 });
  }
  return out.sort((x, y) => x.ratio - y.ratio);
}"""


def check_accessibility(h: Harness):
    numbers, evidence, ok = {}, [], True
    ctx, page, log = h.context()
    try:
        page.wait_for_timeout(400)  # let colour transitions (0.15 s) settle
        rows = page.evaluate(CONTRAST_JS)
        page.goto(f"{h.base}/offline.html")
        rows += [dict(r, selector="offline.html " + r["selector"]) for r in page.evaluate(CONTRAST_JS)]
        h.open(page, "debug=1&nosw=1")
        rows.sort(key=lambda r: (r["ratio"], r["selector"]))
        failing = [r for r in rows if r["ratio"] < 4.5]
        numbers["contrast"] = {"elements": len(rows), "min": rows[0] if rows else None, "below4_5": failing}
        ok &= bool(rows) and not failing
        groups = page.evaluate("""() => [...document.querySelectorAll('[role=radiogroup]')].map(g => {
          const radios = [...g.querySelectorAll('[role=radio]')];
          return { label: g.getAttribute('aria-label'), radios: radios.length, tabZero: radios.filter(r => r.tabIndex === 0).length };
        })""")
        roving = {}
        for gid in ("species-rows", "mode-group", "backend-group"):
            page.focus(f"#{gid} [role=radio][tabindex='0']")
            page.keyboard.press("End")
            end = page.evaluate("document.activeElement.textContent.trim()")
            page.keyboard.press("Home")
            home = page.evaluate("document.activeElement.textContent.trim()")
            roving[gid] = {"end": end, "home": home}
        page.evaluate("window.__spun.setBackend('2d'); window.__spun.setMode('dusk')")
        h.open(page, "debug=1&nosw=1")
        numbers["radiogroups"] = groups
        numbers["homeEnd"] = roving
        ok &= len(groups) >= 3 and all(g["tabZero"] == 1 and g["radios"] > 1 for g in groups)
        ok &= all(v["end"] != v["home"] for v in roving.values())
        rings = {}
        for target, check in (("chip", "document.activeElement?.classList.contains('chip')"), ("stage", "document.activeElement?.id === 'web-canvas'")):
            for _ in range(30):
                page.keyboard.press("Tab")
                if page.evaluate(check):
                    break
            rings[target] = page.evaluate("""() => { const cs = getComputedStyle(document.activeElement);
              return { focused: document.activeElement.id || document.activeElement.className, outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0, boxShadow: cs.boxShadow !== 'none' }; }""")
        numbers["focusRing"] = rings
        ok &= all(r["outline"] or r["boxShadow"] for r in rings.values())
        aria = page.evaluate("""() => { const live = document.querySelector('[aria-live]'); const c = document.querySelector('#web-canvas');
          return { live: live?.getAttribute('aria-live'), canvasTabIndex: c.tabIndex, canvasLabel: Boolean(c.getAttribute('aria-label')),
                   globals: Object.keys(window).filter(k => k.startsWith('__')) }; }""")
        numbers["aria"] = aria
        ok &= aria["live"] == "polite" and aria["canvasTabIndex"] == 0 and aria["canvasLabel"]
        layout = {}
        for width in (1280, 1100, 720, 390):
            page.set_viewport_size({"width": width, "height": 800})
            page.wait_for_timeout(100)
            layout[str(width)] = page.evaluate("""() => { const bar = document.querySelector('.topbar'); const title = document.querySelector('.brand-title');
              const rows = getComputedStyle(bar).gridTemplateRows.split(' ').filter(Boolean).length;
              const lineHeight = parseFloat(getComputedStyle(title).lineHeight) || parseFloat(getComputedStyle(title).fontSize);
              const groups = [...bar.children].filter(c => !c.matches('.brand, .status-pill')).length;
              return { scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth, headerRows: rows,
                       headerHeight: Math.round(bar.getBoundingClientRect().height), brandTitleLines: Math.round(title.getBoundingClientRect().height / lineHeight),
                       controlGroups: groups }; }""")
        numbers["layout"] = layout
        ok &= all(v["scrollWidth"] <= v["viewport"] and v["controlGroups"] <= 4 for v in layout.values())
        ok &= all(layout[w]["headerRows"] == 1 and layout[w]["brandTitleLines"] == 1 for w in ("1280", "1100"))
        page.set_viewport_size({"width": 1280, "height": 800})
        page.screenshot(path=str(OUT / "layout-1280.png")); evidence.append("layout-1280.png")
        page.goto(f"{h.base}/?nosw=1")
        page.wait_for_load_state("load")
        numbers["debugGlobalWithoutFlag"] = page.evaluate("'__spun' in window")
        ok &= not numbers["debugGlobalWithoutFlag"] and not log["errors"]
        return ok, numbers, evidence
    finally:
        ctx.close()


CHECKS = [
    ("cold-load", "Cold load", check_cold_load),
    ("all-species", "All species, both backends", check_all_species),
    ("parity", "2D/GL parity", check_parity),
    ("zero-uploads", "Zero uploads while growing", check_zero_uploads),
    ("settle-and-stop", "Settle-and-stop", check_settle),
    ("eating", "Eating (argiope, golden)", check_eating),
    ("dew", "Dew and glue", check_dew),
    ("cap-and-fit", "Cap and fit", check_cap_fit),
    ("reduced-motion", "Reduced motion", check_reduced_motion),
    ("fallback", "Fallback and persistence", check_fallback),
    ("context-loss", "Context loss", check_context_loss),
    ("sw-install", "Service worker install", check_sw_install),
    ("offline", "Offline", check_offline),
    ("mobile", "Mobile 390x844", check_mobile),
    ("keyboard", "Keyboard", check_keyboard),
    ("accessibility", "Accessibility and layout", check_accessibility),
    ("performance", "Performance (12 growing webs)", check_performance),
]


# ---------------------------------------------------------------- report

def brief_numbers(numbers: dict) -> str:
    text = json.dumps(numbers, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= 400 else text[:397] + "..."


def write_readme(report: dict) -> None:
    env = report["environment"]
    lines = ["# Web verification", "", "Generated by `tools/verify_web.py`; do not edit by hand.", "", "## Environment", ""]
    for key in ("browserVersion", "channel", "launchFlags", "glRenderer", "softwareRenderer", "webgl2", "headless"):
        lines.append(f"- {key}: `{env.get(key)}`")
    if env.get("softwareRenderer"):
        lines.append("- The GL renderer is a software rasterizer; performance numbers are not representative and no 60 fps claim is made.")
    lines += ["", "## Checks", "", "| Check | Status | Numbers | Evidence |", "|---|---|---|---|"]
    for check in report["checks"]:
        evidence = ", ".join(f"[{name}]({name})" for name in check["evidence"]) or "—"
        numbers = brief_numbers(check["numbers"]).replace("|", "\\|")
        lines.append(f"| {check['title']} | {check['status']} | `{numbers}` | {evidence} |")
    lines += ["", "## Not run / why", ""]
    skipped = [c for c in report["checks"] if c["status"] == "NOT RUN"]
    lines += [f"- {c['title']}: {c['numbers'].get('reason', 'not run')}" for c in skipped] or ["- None."]
    lines.append("")
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    index = json.loads((WEB / "specimens" / "index.json").read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    port = free_port()
    server = subprocess.Popen([sys.executable, str(ROOT / "tools" / "serve.py"), "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    report = {"environment": {}, "checks": []}
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            harness = Harness(playwright, base, index)
            try:
                harness.start()
            except Exception as error:  # noqa: BLE001 - no browser automation at all
                report["environment"] = {"browser": None, "error": str(error).splitlines()[0]}
                for key, title, _ in CHECKS:
                    report["checks"].append({"id": key, "title": title, "status": "NOT RUN",
                                             "numbers": {"reason": "no browser automation available"}, "evidence": []})
            else:
                report["environment"] = harness.env
                for key, title, fn in CHECKS:
                    print(f"[verify_web] {title} ...", flush=True)
                    try:
                        passed, numbers, evidence = fn(harness)
                        status = "NOT RUN" if passed is None else ("PASS" if passed else "FAIL")
                    except Exception as error:  # noqa: BLE001 - a crashing check is a failing check
                        status, numbers, evidence = "FAIL", {"error": str(error).splitlines()[0],
                                                             "trace": traceback.format_exc(limit=2).splitlines()[-1]}, []
                    report["checks"].append({"id": key, "title": title, "status": status, "numbers": numbers, "evidence": evidence})
                    print(f"[verify_web]   {status}", flush=True)
                harness.browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(report)
    failed = [c["id"] for c in report["checks"] if c["status"] == "FAIL"]
    print(f"[verify_web] {len(report['checks']) - len(failed)} of {len(report['checks'])} checks not failing; failed: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
