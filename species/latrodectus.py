"""Latrodectus hasselti: retreat in the corner of a weathered rail, tangle and gumfoots."""

from spun.snares import CobwebParameters, cobweb

GROUND = tuple((x, 1100 + 9*((x*37) % 11)/11 - 4) for x in range(0, 1601, 80))

SPEC = CobwebParameters(
    id="redback-spider", width=1600, height=1200, mm_per_px=0.3, duration=24,
    rail=(250.0, 140.0, 226.0), post_width=86,
    ground=GROUND,
    litter=((300, 58, -0.2), (352, 44, 2.9), (560, 50, 3.0), (640, 66, -0.3),
            (770, 52, 0.25), (990, 62, 2.8), (1060, 40, -0.15), (1180, 70, -0.1),
            (1420, 48, 3.3), (1510, 60, 0.2)),
    retreat=(335.0, 262.0, 78.0, 56.0),
    tangle_box=(270.0, 250.0, 1250.0, 640.0), depth=240.0,
    points=(78, 97), retreat_segments=(100, 131), gumfoot=(14, 19),
)


def build():
    return cobweb(SPEC)
