"""Trichonephila edulis: a deep golden orb with a neighbouring barrier web."""

import math

from spun.kinds import BY_NAME, COLORS
from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec

# The barrier stands between the orb's right frame and the right-hand branch.
BOX = ((1045, 1215), (520, 1340), (-110, 110))


def _barrier(builder, rays, hub, anchors, rng, spec):
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


SPEC = OrbParameters(
    id="golden-orb-weaver", width=1300, height=1700,
    polygon=((325, 317), (814, 272), (991, 514), (1037, 771), (1047, 1074),
             (899, 1438), (482, 1535), (150, 1303), (111, 960), (118, 690),
             (202, 439)),
    radii_min=38, radii_max=46, hub_fraction=0.30,
    spacing_outer=7.4, spacing_inner=6.3, free_radius=50,
    auxiliary_spacing=26, mm_per_px=0.8, duration=42,
    lower_anchor=6, golden=True, pose="head-down", extra=_barrier,
    branches=(
        BranchSpec(
            controls=((60, 60), (220, 140), (420, 175), (640, 160), (860, 110),
                      (1060, 30)),
            anchors=((0, 0.30), (1, 0.71)),
            leaves=((0.12, 84, 0.9), (0.82, 90, -0.9))),
        BranchSpec(
            controls=((1110, 150), (1185, 480), (1235, 800), (1215, 1200),
                      (1250, 1640)),
            anchors=((2, 0.21), (3, 0.41), (4, 0.63)),
            leaves=((0.08, 88, -2.0), (0.86, 96, 2.6))),
        BranchSpec(
            controls=((1250, 1690), (1000, 1620), (720, 1600), (420, 1640),
                      (160, 1690)),
            anchors=((5, 0.34), (6, 0.69)),
            leaves=((0.52, 98, -1.2),)),
        BranchSpec(
            controls=((30, 1560), (40, 1250), (30, 950), (55, 650), (100, 360)),
            anchors=((7, 0.22), (8, 0.50), (9, 0.73), (10, 0.91)),
            leaves=((0.36, 85, -0.6), (0.62, 92, -1.3))),
    ),
)


def build():
    return build_orb(SPEC)
