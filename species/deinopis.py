"""Deinopis subrufa: a stick-like spider hanging head-down, her net held in four legs."""

from spun.snares import NetParameters, net_casting

# A slightly rising eucalypt twig; her drop line and two side stays hang from it and
# the Y arms spread to the net's upper corners.
SPEC = NetParameters(
    id="net-casting-spider", width=1000, height=1400, mm_per_px=0.12, duration=18,
    twig=((60, 300), (250, 282), (470, 250), (690, 226), (880, 176), (960, 130)),
    leaves=((0.93, 96, -2.3), (0.08, 88, 2.2), (0.55, 84, -0.9)),
    rest=(505.0, 720.0), stays=(300.0, 720.0),
)


def build():
    return net_casting(SPEC)
