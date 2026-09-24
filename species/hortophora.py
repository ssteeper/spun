"""Hortophora transmarina: the dusk-built reference orb."""

from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec

SPEC = OrbParameters(
    id="garden-orb-weaver", width=1200, height=1600,
    polygon=((432, 330), (746, 344), (985, 507), (1095, 790),
             (1000, 1085), (740, 1250), (460, 1265), (224, 1092),
             (110, 818), (190, 520)),
    radii_min=20, radii_max=24, hub_fraction=0.49,
    spacing_outer=14, spacing_inner=11, free_radius=76,
    auxiliary_spacing=42, mm_per_px=0.6, duration=28,
    lower_anchor=6,
    branches=(
        BranchSpec(
            controls=((555, 20), (570, 95), (565, 175), (565, 245), (600, 280)),
            anchors=((0, 0.84), (1, 0.96)),
            leaves=((0.34, 95, -2.3),)),
        BranchSpec(
            controls=((1185, 125), (1150, 330), (1120, 530), (1110, 790),
                      (1070, 1030), (980, 1305)),
            anchors=((2, 0.36), (3, 0.54), (4, 0.77)),
            leaves=((0.32, 95, 1.4), (0.69, 90, 0.6))),
        BranchSpec(
            controls=((600, 1580), (610, 1520), (655, 1450), (720, 1385),
                      (800, 1365)),
            anchors=((5, 0.82), (6, 0.48)),
            leaves=((0.25, 100, 2.9),)),
        BranchSpec(
            controls=((20, 260), (90, 360), (160, 520), (150, 750),
                      (180, 1010), (240, 1300)),
            anchors=((7, 0.91), (8, 0.65), (9, 0.34)),
            leaves=((0.45, 90, -2.65), (0.75, 95, 2.35))),
    ),
)


def build():
    return build_orb(SPEC)
