"""Austracantha minax: three small orbs built in turn on shared support lines."""

import math

from spun.kinds import BY_NAME, COLORS
from spun.orb import OrbParameters, build_colony
from spun.scaffold import BranchSpec, frame_polygon

MM_PER_PX = 0.35
TUFT_SPACING = 20/MM_PER_PX
TUFT_COLOR = tuple(bytes.fromhex(COLORS["tuft"][1:]))


def _tufts(builder, rays, hub, anchors, rng, spec, frames):
    """Walk her own frame and knot a curled white tuft every ~20 mm (±25%)."""
    graph = builder.graph
    width = BY_NAME["TUFT"].width
    for frame in frames:
        path = list(graph.threads[frame].path)
        points = [graph.position(node) for node in path]
        cumulative = [0.0]
        for a, b in zip(points, points[1:]):
            cumulative.append(cumulative[-1]+math.dist(a, b))
        position = TUFT_SPACING*rng.uniform(0.5, 1.0)
        while position < cumulative[-1]-8:
            segment = max(i for i, c in enumerate(cumulative[:-1]) if c <= position)
            a, b = points[segment], points[segment+1]
            span = cumulative[segment+1]-cumulative[segment]
            along = position-cumulative[segment]
            if 3 < along < span-5:
                ux, uy = (b[0]-a[0])/span, (b[1]-a[1])/span
                start = (a[0]+ux*along, a[1]+uy*along)
                # Curl outward, away from the hub, back onto the frame 2–3 px on.
                hx, hy = graph.position(hub)
                nx, ny = -uy, ux
                if (start[0]-hx)*nx+(start[1]-hy)*ny < 0:
                    nx, ny = -nx, -ny
                # A half-ellipse loop out from the frame and back, 6–12 px long.
                count = int(rng.integers(6, 11))
                total = rng.uniform(6, 12)
                gap = rng.uniform(2.2, 3.0)
                wobbles = [1+0.06*math.sin(3*math.pi*j/count+rng.uniform(-0.4, 0.4))
                           for j in range(1, count)]

                def loop(height):
                    offsets = [(0.0, 0.0)]
                    for j, wobble in zip(range(1, count), wobbles):
                        theta = math.pi*(1-j/count)
                        offsets.append((gap/2*(1+math.cos(theta)),
                                        height*math.sin(theta)*wobble))
                    return offsets+[(gap, 0.0)]

                height = total/2
                for _ in range(4):
                    offsets = loop(height)
                    height *= total/sum(math.dist(a, b) for a, b in zip(offsets, offsets[1:]))
                curl = [(start[0]+ux*across+nx*lift, start[1]+uy*across+ny*lift)
                        for across, lift in loop(height)[1:-1]]
                first = graph.attach(frame, start)
                last = graph.attach(frame, (start[0]+ux*gap, start[1]+uy*gap))
                if first != last:
                    builder.walk_to(first)
                    tuft = builder.spin([first, *curl, last], "TUFT")
                    graph.threads[tuft].styles = [(width, TUFT_COLOR, 0.9)]*count
            position += TUFT_SPACING*rng.uniform(0.75, 1.25)
    return hub


def _ring(cx, cy, corners):
    return tuple((round(cx+r*math.cos(math.radians(a))), round(cy+r*math.sin(math.radians(a))))
                 for a, r in corners)


# The centre orb hangs in a U-shaped fork below a crossing twig.
C = _ring(800, 560, ((-112, 215), (-65, 205), (-20, 210), (25, 205), (70, 215),
                     (112, 210), (158, 205), (203, 210)))
CENTRE_BRANCHES = (
    BranchSpec(controls=((560, 330), C[0], C[1], (1050, 330)),
               anchors=((0, C[0]), (1, C[1])),
               leaves=((0.04, 80, -2.2), (0.96, 84, -0.9))),
    BranchSpec(controls=((600, 150), (560, 470), (600, 720), (800, 830), (1000, 720),
                         (1045, 470), (1000, 150)),
               anchors=tuple((i, C[i]) for i in (7, 6, 5, 4, 3, 2)),
               leaves=((0.5, 90, 1.7),)),
)


def _on_edge(i, j, t):
    return (C[i][0]+t*(C[j][0]-C[i][0]), C[i][1]+t*(C[j][1]-C[i][1]))


# Left and right orbs each tie one corner onto the centre orb's frame.
L = _ring(330, 700, ((-118, 210), (-70, 215), (0, 0), (15, 205), (60, 210), (105, 215),
                     (150, 205), (195, 210)))
L_SHARED = {2: _on_edge(6, 7, 0.45)}
LEFT_BRANCHES = (
    BranchSpec(controls=((530, 380), (420, 440), (250, 480), (140, 600), (100, 780),
                         (160, 950), (240, 1120)),
               anchors=tuple((i, L[i]) for i in (1, 0, 7, 6)),
               leaves=((0.02, 84, -1.3), (0.97, 88, 2.0))),
    BranchSpec(controls=((40, 1000), (250, 960), (400, 940), (520, 840), (590, 760)),
               anchors=tuple((i, L[i]) for i in (5, 4, 3)),
               leaves=((0.12, 86, 2.6),)),
)
R = _ring(1270, 700, ((-115, 210), (-65, 205), (-15, 215), (30, 205), (75, 210),
                      (120, 215), (165, 205), (0, 0)))
R_SHARED = {7: _on_edge(2, 3, 0.5)}
RIGHT_BRANCHES = (
    BranchSpec(controls=((1070, 380), (1180, 440), (1350, 470), (1460, 600), (1500, 780),
                         (1440, 950), (1360, 1120)),
               anchors=tuple((i, R[i]) for i in (0, 1, 2, 3)),
               leaves=((0.35, 86, -1.4), (0.97, 90, 1.0))),
    BranchSpec(controls=((1560, 1000), (1350, 950), (1200, 940), (1080, 840), (1010, 760)),
               anchors=tuple((i, R[i]) for i in (4, 5, 6)),
               leaves=((0.10, 84, 0.6),)),
)


def _orb(suffix, branches, shared, lower, hub_fraction):
    return OrbParameters(
        id="christmas-jewel-spider"+suffix, width=1600, height=1200,
        polygon=frame_polygon(branches, shared), radii_min=13, radii_max=16,
        hub_fraction=hub_fraction, spacing_outer=10, spacing_inner=8, free_radius=30,
        auxiliary_spacing=28, mm_per_px=MM_PER_PX, duration=36, lower_anchor=lower,
        branches=branches, extra=_tufts, shared=tuple(shared))


SPEC = _orb("", CENTRE_BRANCHES, {}, 5, 0.50)
SPECS = (SPEC, _orb("-2", LEFT_BRANCHES, L_SHARED, 5, 0.46),
         _orb("-3", RIGHT_BRANCHES, R_SHARED, 4, 0.53))


def build():
    return build_colony(SPECS)
