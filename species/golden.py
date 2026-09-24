"""Trichonephila edulis: a deep golden orb with a neighbouring barrier web."""

import math

from spun.kinds import BY_NAME, COLORS
from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec, frame_polygon

# The barrier curtain hangs beyond the right-hand limb.
BOX = ((1125, 1225), (520, 1340), (-110, 110))


def _barrier(builder, rays, hub, anchors, rng, spec, frames):
    """Spin a projected 3-D barrier, starting from the orb's right-hand anchors."""
    graph = builder.graph
    count = int(rng.integers(52, 67))
    (x0, x1), (y0, y1), (z0, z1) = BOX
    points = [(float(rng.uniform(x0, x1)), float(rng.uniform(y0, y1)),
               float(rng.uniform(z0, z1))) for _ in range(count)]
    # Oblique projection: depth slides points sideways and slightly down.
    nodes = [graph.node((x + 0.32*z, y + 0.12*z)) for x, y, z in points]
    color = tuple(bytes.fromhex(COLORS["golden_radius"][1:]))
    width = BY_NAME["TANGLE"].width

    def depth(*indices):
        return sum((points[i][2]-z0)/(z1-z0) for i in indices)/len(indices)

    def spin(start, end, near):
        builder.walk_to(start)
        thread = builder.spin([start, end], "TANGLE")
        graph.threads[thread].styles = [(width, color, 0.35 + 0.25*near)]

    def distance(a, b):
        return sum((v-w)**2 for v, w in zip(points[a], points[b]))

    # A nearest-edge spanning tree lets her reach every point along silk.
    start = min(range(count), key=lambda i: math.dist(graph.position(anchors[3]),
                                                      graph.position(nodes[i])))
    spin(anchors[3], nodes[start], depth(start))
    connected = [start]
    edges = set()
    while len(connected) < count:
        _, source, destination = min((distance(i, j), i, j) for i in connected
                                     for j in range(count) if j not in connected)
        spin(nodes[source], nodes[destination], depth(source, destination))
        edges.add((min(source, destination), max(source, destination)))
        connected.append(destination)
    # Two or three nearest partners per point make a mesh, not a chain.
    for i in range(count):
        neighbours = sorted((distance(i, j), j) for j in range(count) if j != i)
        for _, j in neighbours[:2 + (i % 2)]:
            edge = (min(i, j), max(i, j))
            if edge not in edges:
                spin(nodes[i], nodes[j], depth(i, j))
                edges.add(edge)
    # Long stays bind the curtain to the orb's frame anchors above and below.
    for anchor, target_y in ((2, 540), (4, 1000), (5, 1320)):
        target = min(range(count), key=lambda i: abs(points[i][1]-target_y)
                     + 0.3*abs(points[i][0]-x0))
        spin(anchors[anchor], nodes[target], depth(target))
    return hub


# A leaning sapling on the left forks into a crown bough over the orb; a
# second limb sweeps up from the ground on the right. The orb hangs between.
BRANCHES = (
    BranchSpec(
        controls=((90, 1700), (100, 1450), (80, 1180), (111, 960), (100, 700),
                  (160, 440), (260, 160)),
        anchors=((7, (150, 1303)), (8, (111, 960)), (9, (118, 690)), (10, (202, 439))),
        leaves=((0.93, 84, -2.2), (0.30, 90, -2.0))),
    BranchSpec(
        controls=((215, 280), (420, 255), (620, 245), (814, 272), (930, 300),
                  (1060, 280)),
        anchors=((0, (325, 317)), (1, (814, 272))),
        leaves=((0.55, 88, -1.9), (0.97, 92, -0.5))),
    BranchSpec(
        controls=((560, 1700), (640, 1600), (899, 1438), (1060, 1200), (1100, 960),
                  (1075, 700), (990, 470)),
        anchors=((6, (610, 1560)), (5, (899, 1438)), (4, (1047, 1074)),
                 (3, (1037, 771)), (2, (991, 514))),
        leaves=((0.95, 90, -2.0), (0.28, 96, 0.4))),
)

SPEC = OrbParameters(
    id="golden-orb-weaver", width=1300, height=1700,
    polygon=frame_polygon(BRANCHES),
    radii_min=38, radii_max=46, hub_fraction=0.30,
    spacing_outer=7.4, spacing_inner=6.3, free_radius=50,
    auxiliary_spacing=26, mm_per_px=0.8, duration=42,
    lower_anchor=6, golden=True, pose="head-down", extra=_barrier,
    branches=BRANCHES,
)


def build():
    return build_orb(SPEC)
