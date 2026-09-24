"""Arachnura higginsi: an open signal sector hung with woolly egg sacs."""

import math

from spun.kinds import COLORS
from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec, frame_polygon


def _egg_sacs(builder, rays, hub, anchors, rng, spec, frames):
    """Weave each sac from a live attachment on the otherwise empty signal spoke."""
    graph = builder.graph
    # Only the seed signal spoke terminates on the bridge inside the open V.
    bridge = next(thread for thread in graph.threads if thread.kind == "BRIDGE")
    signal = next(ray for ray in rays if ray.foot in bridge.path)
    origin = graph.position(hub)
    end = graph.position(signal.foot)
    color = tuple(bytes.fromhex(COLORS["eggsac_arachnura"][1:]))

    def weave(path, width, alpha):
        thread = builder.spin(path, "EGGSAC")
        graph.threads[thread].styles = [(width, color, alpha)]*(len(graph.threads[thread].path)-1)

    count = int(rng.integers(5, 9))
    lowest = None
    for number in range(count-1, -1, -1):
        fraction = 0.115 + 0.103*number
        host = graph.attach(signal.thread,
                            (origin[0]+fraction*(end[0]-origin[0]),
                             origin[1]+fraction*(end[1]-origin[1])))
        hx, hy = graph.position(host)
        # An oval hung on the line above its tie: long axis along the line.
        ux, uy = (end[0]-origin[0]), (end[1]-origin[1])
        norm = math.hypot(ux, uy)
        ux, uy = ux/norm, uy/norm
        half_length = rng.uniform(17, 20)
        half_width = rng.uniform(11, 13.5)
        tilt = rng.uniform(-0.12, 0.12)
        ax, ay = ux*math.cos(tilt)-uy*math.sin(tilt), ux*math.sin(tilt)+uy*math.cos(tilt)
        centre = (hx+ax*half_length, hy+ay*half_length)
        outline = [host]
        for j in range(1, 16):
            theta = math.pi+math.tau*j/16
            wool = 1+rng.uniform(-0.05, 0.05)
            outline.append(graph.node(
                (centre[0]+(ax*half_length*math.cos(theta)-ay*half_width*math.sin(theta))*wool,
                 centre[1]+(ay*half_length*math.cos(theta)+ax*half_width*math.sin(theta))*wool)))
        lowest = host
        builder.walk_to(host)
        weave(outline+[host], 1.35, 0.95)
        # Woolly hatching: slanted strokes across the sac between outline points.
        for first, last in ((2, 13), (3, 11), (5, 12), (4, 9), (6, 10), (7, 9)):
            builder.walk_to(outline[first])
            weave([outline[first], outline[last]], 0.65, 0.62)
    # She hangs at the bottom of the string, tail up along the signal line.
    builder.walk_to(lowest)
    return lowest


_HALF_OPENING = math.radians(28)

# Two stems lean together into a V below a level twig; the orb fills the
# wedge and its open signal sector points up at the twig.
BRANCHES = (
    BranchSpec(
        controls=((20, 330), (300, 300), (600, 290), (900, 300), (1180, 340)),
        anchors=((0, (450, 340)), (1, (760, 340))),
        leaves=((0.10, 84, -1.0), (0.93, 90, -2.0))),
    BranchSpec(
        controls=((1150, 200), (1075, 420), (1045, 800), (900, 1080), (700, 1280),
                  (610, 1360)),
        anchors=((2, (995, 420)), (3, (1000, 640)), (4, (950, 900)), (5, (760, 1150)),
                 (6, (600, 1290))),
        leaves=((0.45, 92, 0.2),)),
    BranchSpec(
        controls=((80, 200), (130, 420), (180, 800), (320, 1100), (480, 1290),
                  (590, 1360)),
        anchors=((7, (380, 1060)), (8, (240, 760)), (9, (215, 420))),
        leaves=((0.40, 88, 2.9), (0.75, 84, 2.4))),
)

SPEC = OrbParameters(
    id="scorpion-tailed-spider", width=1200, height=1600,
    polygon=frame_polygon(BRANCHES),
    radii_min=17, radii_max=21, hub_fraction=0.50,
    spacing_outer=11, spacing_inner=9, free_radius=44,
    auxiliary_spacing=36, mm_per_px=0.35, duration=26,
    lower_anchor=6, pose="hub-tail",
    open_sectors=((-math.pi/2-_HALF_OPENING, -math.pi/2+_HALF_OPENING),),
    branches=BRANCHES,
    extra=_egg_sacs,
)


def build():
    return build_orb(SPEC)
