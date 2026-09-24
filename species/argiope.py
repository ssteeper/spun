"""Argiope keyserlingi: a four-armed, zig-zag St Andrew's Cross."""

import math

from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec


def _stabilimentum(builder, rays, hub, anchors, rng, spec):
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


SPEC = OrbParameters(
    id="st-andrews-cross", width=1200, height=1600,
    polygon=((334, 471), (652, 402), (899, 455), (988, 706), (1018, 965),
             (859, 1199), (571, 1248), (302, 1194), (215, 944), (164, 689)),
    radii_min=22, radii_max=26, hub_fraction=0.46,
    spacing_outer=11, spacing_inner=9, free_radius=46,
    auxiliary_spacing=34, mm_per_px=0.5, duration=30,
    lower_anchor=6, pose="hub-x", extra=_stabilimentum,
    branches=(
        BranchSpec(
            controls=((60, 1580), (70, 1150), (110, 700), (260, 390), (560, 260),
                      (880, 290), (1150, 170)),
            anchors=((8, 0.29), (9, 0.42), (0, 0.56), (1, 0.77), (2, 0.86)),
            leaves=((0.12, 92, -0.7), (0.49, 86, -2.3), (0.68, 90, -1.5),
                    (0.95, 84, 1.0))),
        BranchSpec(
            controls=((1180, 300), (1120, 650), (1090, 980), (950, 1270), (640, 1370),
                      (300, 1330), (110, 1450)),
            anchors=((3, 0.22), (4, 0.37), (5, 0.55), (6, 0.75), (7, 0.87)),
            leaves=((0.08, 90, -2.3), (0.46, 94, 0.5), (0.65, 88, 1.4))),
    ),
)


def build():
    return build_orb(SPEC)
