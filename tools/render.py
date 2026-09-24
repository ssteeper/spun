"""Render final-state specimen plates from the registered Python construction program."""

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from species import SPECIES
from spun.kinds import ENV, INVISIBLE
from spun.silkfile import NEVER, read_silk

SUPERSAMPLE = 4
BACKGROUND = (5, 6, 12)


def _stroke(layer, row, multiplier=SUPERSAMPLE):
    x0, y0, x1, y1 = (int(row[key])/4*multiplier for key in ("x0", "y0", "x1", "y1"))
    width_px = max(int(row["width"])/32, 0.55)
    diameter = max(1, round(max(width_px, 1)*multiplier))
    radius = diameter/2
    alpha = round(int(row["alpha"])*min(width_px, 1))
    margin = diameter+2
    min_x = max(0, int(min(x0, x1)-margin))
    min_y = max(0, int(min(y0, y1)-margin))
    max_x = min(layer.width, int(max(x0, x1)+margin+1))
    max_y = min(layer.height, int(max(y0, y1)+margin+1))
    if max_x <= min_x or max_y <= min_y:
        return
    tile = Image.new("RGBA", (max_x-min_x, max_y-min_y), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    color = (int(row["r"]), int(row["g"]), int(row["b"]), alpha)
    first, second = (x0-min_x, y0-min_y), (x1-min_x, y1-min_y)
    draw.line((first, second), fill=color, width=diameter)
    for x, y in (first, second):
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    layer.alpha_composite(tile, dest=(min_x, min_y))


def plate(result, width, height, *, dawn=False):
    size = (width*SUPERSAMPLE, height*SUPERSAMPLE)
    env = Image.new("RGBA", size, (0, 0, 0, 0))
    silk = Image.new("RGBA", size, (0, 0, 0, 0))
    for row in result.records:
        if row["death"] != NEVER or row["flags"] & INVISIBLE:
            continue
        _stroke(env if row["flags"] & ENV else silk, row)
    native = (width, height)
    env = env.resize(native, Image.Resampling.LANCZOS)
    silk = silk.resize(native, Image.Resampling.LANCZOS)
    if dawn:
        top, bottom = (11, 17, 36), (29, 21, 33)
        ramp = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
        gradient = np.repeat(np.uint8(np.rint(np.array(top)[None, None, :]*(1-ramp) +
                                                  np.array(bottom)[None, None, :]*ramp)), width, axis=1)
        base = Image.fromarray(gradient, "RGB").convert("RGBA")
    else:
        base = Image.new("RGBA", native, (*BACKGROUND, 255))
    # Add a blurred, premultiplied silk glow before drawing sharp silk.
    glow = np.asarray(silk.filter(ImageFilter.GaussianBlur(14)), dtype=np.float32)
    base_rgb = np.array(base.convert("RGB"), dtype=np.float32)
    base_rgb += glow[..., :3]*(glow[..., 3:4]/255)*(0.6 if dawn else 0.5)
    base = Image.fromarray(np.uint8(np.clip(np.rint(base_rgb), 0, 255)), "RGB").convert("RGBA")
    base.alpha_composite(env)
    base.alpha_composite(silk)
    return base.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--only", choices=sorted(SPECIES))
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--dawn", action="store_true")
    args = parser.parse_args()
    output = ROOT / "renders"
    output.mkdir(exist_ok=True)
    names = sorted(SPECIES) if args.all else [args.only]
    for name in names:
        result = SPECIES[name]()
        decoded = read_silk(result.data)
        stem = SPECIES[name].__module__.rsplit(".", 1)[-1]
        target = output / f"{stem}_{'dawn' if args.dawn else 'dusk'}.png"
        plate(result, decoded.width, decoded.height, dawn=args.dawn).save(target)
        print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
