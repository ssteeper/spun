"""Argiope keyserlingi: a four-armed, zig-zag St Andrew's Cross."""

import math

from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec, frame_polygon


def _stabilimentum(builder, rays, hub, anchors, rng, spec, frames):
    """Weave four diagonal bands, tied to live radial silk at both ends."""
    graph = builder.graph
    origin = graph.position(hub)
    inner = 0.45 * spec.free_radius + 6
    for diagonal in (math.pi / 4, 3 * math.pi / 4,
                     5 * math.pi / 4, 7 * math.pi / 4):
        ray = min(rays, key=lambda spoke: abs((spoke.angle - diagonal + math.pi) % math.tau - math.pi))
        dx = math.cos(ray.angle)
        dy = math.sin(ray.angle)
        outer = 0.55 * ray.radius

        def on_radius(distance):
            return (origin[0] + distance * dx, origin[1] + distance * dy)

        start = graph.attach(ray.thread, on_radius(inner))
        end = graph.attach(ray.thread, on_radius(outer))
        builder.walk_to(start)
        zig = [start]
        for step in range(1, int((outer - inner) / 3.5) + 1):
            distance = inner + step * 3.5
            if distance >= outer - 1:
                break
            side = 8 if step % 2 else -8
            zig.append((origin[0] + distance * dx - side * dy,
                        origin[1] + distance * dy + side * dx))
        zig.append(end)
        thread = builder.spin(zig, "STABILIMENTUM")
        graph.threads[thread].styles = [(1.9, (246, 249, 255), 1.0)] * (len(zig) - 1)
    return hub


# One stem arches up the left and over the top; a cross twig curls in from
# the right and under the web.
BRANCHES = (
    BranchSpec(
        controls=((60, 1580), (120, 1150), (150, 900), (150, 690), (290, 470),
                  (652, 380), (1150, 380)),
        anchors=((8, (215, 944)), (9, (164, 689)), (0, (334, 471)), (1, (652, 402)),
                 (2, (899, 455))),
        leaves=((0.12, 92, -0.7), (0.58, 86, -2.3), (0.95, 84, -0.6))),
    BranchSpec(
        controls=((1180, 250), (1060, 700), (1070, 960), (900, 1240), (600, 1300),
                  (302, 1250), (100, 1420)),
        anchors=((3, (988, 706)), (4, (1018, 965)), (5, (859, 1199)), (6, (571, 1248)),
                 (7, (302, 1194))),
        leaves=((0.06, 90, -2.3), (0.50, 94, 1.3), (0.88, 88, 2.2))),
)

SPEC = OrbParameters(
    id="st-andrews-cross", width=1200, height=1600,
    polygon=frame_polygon(BRANCHES),
    radii_min=22, radii_max=26, hub_fraction=0.46,
    spacing_outer=11, spacing_inner=9, free_radius=46,
    auxiliary_spacing=34, mm_per_px=0.5, duration=30,
    lower_anchor=6, pose="hub-x", extra=_stabilimentum,
    branches=BRANCHES,
)


def build():
    return build_orb(SPEC)
