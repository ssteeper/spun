"""Phonognatha graeffei: an irregular orb with a bound, rolled-leaf retreat."""

import math

from spun.kinds import COLORS
from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec, frame_polygon


def _leaf_retreat(builder, rays, hub, anchors, rng, spec, frames):
    """Haul a curled leaf into the free zone, then lash it to live spokes."""
    graph = builder.graph
    origin = graph.position(hub)
    mean_radius = sum(ray.radius for ray in rays) / len(rays)
    length = 146.0
    center = (origin[0] + 22, origin[1] - 0.12*mean_radius)
    forward = (0.24, -math.sqrt(1-0.24**2))
    normal = (-forward[1], forward[0])

    def point(t, offset=0):
        bend = 3*math.sin(math.pi*t)*math.sin(2*math.pi*t)
        return (center[0] + (t-0.5)*length*forward[0] + (bend+offset)*normal[0],
                center[1] + (t-0.5)*length*forward[1] + (bend+offset)*normal[1])

    def leaf(path, color, width=1.1, alpha=0.95):
        nodes = [node if isinstance(node, int) else graph.node(node) for node in path]
        graph.add_thread(nodes, "LEAF", env=True,
                         styles=[(width, tuple(bytes.fromhex(color[1:])), alpha)]*(len(nodes)-1))

    base = graph.node(point(0))
    tip = graph.node(point(1))
    middle = [graph.node(point(i/16)) for i in range(17)]
    outline = {}
    for side, half_width in ((-1, 31), (1, 27)):
        outline[side] = [graph.node(point(i/16, side*half_width*math.sin(math.pi*i/16)**0.72))
                         for i in range(17)]
    # Both margins return to the same tip and mouth: one continuous curled silhouette.
    leaf(outline[-1] + list(reversed(outline[1][1:-1])) + [base],
         COLORS["leaf"], 1.85)
    leaf(middle, COLORS["leaf_vein"], 1.15)
    # Narrow, nested roll edges suggest a hollow tube rather than a flat green leaf.
    for side, width, color in ((-1, 25, "#8a6440"), (-1, 19, "#805b38"), (-1, 11, "#74522f"),
                               (1, 21, "#a8875a"), (1, 15, "#b09061"), (1, 7, "#957249")):
        lip = [base] + [point(i/16, side*width*math.sin(math.pi*i/16)**0.72)
                        for i in range(1, 16)] + [tip]
        leaf(lip, color, 1.3, 0.88)
    leaf([outline[1][10], outline[1][12], outline[1][14],
          point(0.92, 12), point(0.96, 7), point(0.91, 3), point(0.88, 6)],
         "#c2a074", 1.4)

    # Seven pairs of bent veins terminate exactly on the two leaf margins.
    for i in range(2, 15, 2):
        t = i/16
        span = math.sin(math.pi*t)**0.72
        for side, half_width in ((-1, 31), (1, 27)):
            leaf([middle[i], point(t+0.025, side*half_width*span*0.48), outline[side][i]],
                 COLORS["leaf_vein"], 0.82, 0.82)

    # Each stitch starts on her current live path, terminates at the leaf's edge,
    # and the next begins only after she has walked back along existing silk.
    for i in (3, 5, 8, 11):
        for side in (-1, 1):
            mouth = outline[side][i]
            x, y = graph.position(mouth)
            desired = (math.atan2(y-origin[1], x-origin[0]) + side*0.32) % math.tau
            ray = min(rays, key=lambda spoke: abs((spoke.angle-desired+math.pi) % math.tau-math.pi))
            foot = graph.position(ray.foot)
            dx, dy = foot[0]-origin[0], foot[1]-origin[1]
            span = math.hypot(dx, dy)
            projection = ((x-origin[0])*dx+(y-origin[1])*dy)/span
            distance = min(span-25, max(72, projection+17+rng.uniform(-3, 3)))
            attachment = graph.attach(ray.thread,
                                      (origin[0]+distance*dx/span,
                                       origin[1]+distance*dy/span))
            builder.walk_to(attachment)
            stitch = builder.spin([attachment, mouth], "RETREAT")
            graph.threads[stitch].styles = [(0.6, tuple(bytes.fromhex(COLORS["retreat"][1:])), 0.8)]

    # She settles just inside the downward-facing mouth, reached along the stitches.
    rest = middle[2]
    builder.walk_to(rest)
    return rest


# A forked sapling: the trunk splits into two limbs that cradle the orb and a
# crossing twig carries the bridge.
BRANCHES = (
    BranchSpec(
        controls=((640, 1600), (600, 1400), (420, 1330), (260, 1210), (100, 960),
                  (80, 640), (170, 420)),
        anchors=((6, (494, 1292)), (7, (281, 1168)), (8, (136, 943)), (9, (130, 637)),
                 (10, (188, 456))),
        leaves=((0.97, 86, -1.4), (0.52, 90, 2.9))),
    BranchSpec(
        controls=((660, 1600), (700, 1400), (860, 1300), (1030, 1110), (1120, 820),
                  (1100, 560), (1000, 420)),
        anchors=((5, (815, 1256)), (4, (1004, 1050)), (3, (1064, 682)), (2, (946, 451))),
        leaves=((0.36, 92, 0.5), (0.97, 84, -2.4))),
    BranchSpec(
        controls=((1150, 330), (950, 290), (737, 300), (500, 300), (282, 320),
                  (120, 360)),
        anchors=((0, (282, 344)), (1, (737, 328))),
        leaves=((0.08, 88, -0.4), (0.62, 80, -2.0))),
)

SPEC = OrbParameters(
    id="leaf-curling-spider", width=1200, height=1600,
    polygon=frame_polygon(BRANCHES),
    radii_min=19, radii_max=24, hub_fraction=0.46,
    spacing_outer=12, spacing_inner=10, free_radius=72,
    auxiliary_spacing=38, mm_per_px=0.45, duration=30,
    lower_anchor=6, pose="in-leaf", extra=_leaf_retreat,
    branches=BRANCHES,
)


def build():
    return build_orb(SPEC)
