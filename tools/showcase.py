"""Render the Sunlit showcase images in renders/sunlit/ from the live viewer.

Starts tools/serve.py, drives Chromium through Playwright with the breeze stilled and the scene clock
fixed, and saves JPEG stills: the golden-hour stage, dawn dew close-ups, the light presets and a
contact sheet of the nine ray-marched spiders. Without a hardware GPU Chromium falls back to
SwiftShader, which is slow but produces the same images.
"""
from __future__ import annotations

import argparse
import io
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "renders" / "sunlit"

try:
    from PIL import Image
    from playwright.sync_api import sync_playwright
except ImportError as error:  # pragma: no cover - environment guard
    print(f"showcase.py needs playwright and pillow ({error}).", file=sys.stderr)
    sys.exit(2)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Viewer:
    def __init__(self, browser, base: str, width: int, height: int, scale: float):
        self.page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        self.errors: list[str] = []
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(f"{base}/?debug=1&nosw=1&look=sunlit", wait_until="load")
        self.page.wait_for_function("window.__spun && window.__spun.ready", timeout=60000)
        self.page.evaluate("async () => await window.__spun.ready")
        self.page.add_style_tag(content="#stage-hint,#zoom-hud{display:none!important}")
        self.index = json.loads(self.page.evaluate("fetch('specimens/index.json').then(r => r.text())"))
        self.specs = {spec["id"]: spec for spec in self.index["specimens"]}

    def set(self, **values):
        for path, value in values.items():
            self.page.evaluate("([p, v]) => window.__spun.settings.set(p, v)", [path.replace("__", "."), value])

    def reset(self, mode="dusk", time_s=6.0):
        self.page.evaluate("window.__spun.clear(); window.__spun.settings.resetAll()")
        self.set(quality="ultra", motion=0)
        self.page.evaluate(f"window.__spun.setMode('{mode}'); window.__spun.setSceneTime({time_s}); window.__spun.zoomTo(1, 0, 0)")

    def stage(self):
        return self.page.evaluate("(() => { const r = document.querySelector('#stage').getBoundingClientRect(); return [r.width, r.height]; })()")

    def plant(self, sid, fx=0.5, fy=0.5):
        w, h = self.stage()
        before = self.page.evaluate("window.__spun.stats().instances")
        self.page.evaluate("([id, x, y]) => window.__spun.plant(id, x, y)", [sid, w * fx, h * fy])
        self.page.wait_for_function("n => window.__spun.stats().instances === n", arg=min(12, before + 1))

    def finish(self):
        self.page.evaluate("window.__spun.seek('end')")
        self.settle()

    def settle(self):
        self.page.wait_for_function("!window.__spun.stats().rafActive", timeout=600000)
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    def spider_point(self, sid, k=0):
        placement = self.page.evaluate("window.__spun.stats().placements")[k]
        spec = self.specs[sid]
        rest = spec["spiders"][0]["rest"]
        return (placement["anchorX"] + (rest["x"] - spec["anchor"]["x"]) * placement["scale"],
                placement["anchorY"] + (rest["y"] - spec["anchor"]["y"]) * placement["scale"], placement)

    def zoom(self, level, x, y):
        self.page.evaluate(f"window.__spun.zoomTo({level}, {x}, {y})")
        self.settle()

    def shot(self) -> Image.Image:
        return Image.open(io.BytesIO(self.page.locator("#stage").screenshot())).convert("RGB")


def save(image: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    image.save(path, quality=90, optimize=True, progressive=True)
    print(path.relative_to(ROOT).as_posix(), flush=True)


def hero(v: Viewer):
    v.reset("dusk")
    v.plant("st-andrews-cross", 0.46, 0.5)
    v.finish()
    x, y, _ = v.spider_point("st-andrews-cross")
    v.zoom(1.35, x, y)
    save(v.shot(), "golden-hour.jpg")


def dawn(v: Viewer):
    v.reset("dawn")
    v.plant("golden-orb-weaver", 0.5, 0.52)
    v.finish()
    save(v.shot(), "misty-dawn.jpg")
    _, h = v.stage()
    x, y, _ = v.spider_point("golden-orb-weaver")
    # A stretch of capture spiral below and left of the hub.
    v.zoom(9, x - 0.09 * h, y + 0.12 * h)
    save(v.shot(), "dew-closeup.jpg")


def presets(v: Viewer):
    tiles = []
    for preset, mode in (("golden", "dusk"), ("dawn", "dawn"), ("noon", "dusk"), ("blue", "dusk"), ("moon", "dusk")):
        v.reset(mode)
        v.page.evaluate(f"window.__spun.settings.applyPreset('{mode}', '{preset}')")
        v.set(quality="ultra", motion=0)
        v.plant("garden-orb-weaver", 0.5, 0.5)
        v.finish()
        tiles.append(v.shot())
    # The sixth tile is the Classic look of the same web, for comparison.
    v.reset("dusk")
    v.set(look="classic")
    v.plant("garden-orb-weaver", 0.5, 0.5)
    v.finish()
    tiles.append(v.shot())
    v.set(look="sunlit")
    w, h = tiles[0].size
    thumbs = [tile.resize((w // 2, h // 2), Image.LANCZOS) for tile in tiles]
    sheet = Image.new("RGB", (w // 2 * 3, h // 2 * 2), (5, 6, 12))
    for i, thumb in enumerate(thumbs[:6]):
        sheet.paste(thumb, ((i % 3) * (w // 2), (i // 3) * (h // 2)))
    save(sheet, "light-presets.jpg")


def spiders(v: Viewer):
    tiles = []
    for sid, spec in v.specs.items():
        v.reset("dusk")
        v.set(spiders__size=1.6)
        v.plant(sid, 0.5, 0.5)
        v.finish()
        x, y, placement = v.spider_point(sid)
        glyph = spec["spiders"][0]["glyph"]
        length = glyph["body"][1]["x"] / 0.76
        size = 1 if sid in ("net-casting-spider", "magnificent-spider") else 1.6
        css_per_mm = placement["scale"] * glyph["scale"] / spec["mmPerUnit"] * size
        v.zoom(max(1.0, min(12.0, 190.0 / (length * css_per_mm))), x, y)
        image = v.shot()
        w, h = image.size
        side = min(w, h)
        tiles.append(image.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2)).resize((480, 480), Image.LANCZOS))
    sheet = Image.new("RGB", (480 * 3, 480 * 3), (5, 6, 12))
    for i, tile in enumerate(tiles[:9]):
        sheet.paste(tile, ((i % 3) * 480, (i // 3) * 480))
    save(sheet, "spiders.jpg")


SHOTS = {"hero": hero, "dawn": dawn, "presets": presets, "spiders": spiders}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=list(SHOTS), action="append")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--scale", type=float, default=1.5)
    args = parser.parse_args()
    port = free_port()
    server = subprocess.Popen([sys.executable, str(ROOT / "tools" / "serve.py"), "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--enable-gpu", "--ignore-gpu-blocklist"])
            viewer = Viewer(browser, base, args.width, args.height, args.scale)
            for name in args.only or list(SHOTS):
                SHOTS[name](viewer)
            browser.close()
            if viewer.errors:
                print("\n".join(viewer.errors), file=sys.stderr)
                return 1
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
