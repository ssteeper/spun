"""Hortophora transmarina: the dusk-built reference orb."""

from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec

SPEC = OrbParameters(
    id="garden-orb-weaver", width=1200, height=1600,
    polygon=((346, 331), (781, 361), (1049, 546), (1055, 855), (993, 1179),
             (679, 1424), (318, 1325), (157, 1040), (136, 766), (166, 515)),
    radii_min=17, radii_max=21, hub_fraction=0.40,
    spacing_outer=14, spacing_inner=11, free_radius=70,
    auxiliary_spacing=42, mm_per_px=0.6, duration=28,
    lower_anchor=5,
    branches=(
        BranchSpec(
            controls=((0, 90), (260, 200), (560, 250), (860, 290), (1090, 400),
                      (1190, 560)),
            anchors=((0, 0.30), (1, 0.62), (2, 0.92)),
            leaves=((0.10, 92, -1.2), (0.46, 86, -2.2), (0.78, 90, -0.4))),
        BranchSpec(
            controls=((640, 1600), (900, 1500), (1100, 1250), (1170, 950),
                      (1185, 690)),
            anchors=((3, 0.84), (4, 0.53), (5, 0.11)),
            leaves=((0.30, 95, 0.3), (0.70, 88, -2.6))),
        BranchSpec(
            controls=((260, 1600), (110, 1330), (45, 1050), (40, 780), (70, 500),
                      (130, 300)),
            anchors=((6, 0.17), (7, 0.43), (8, 0.65), (9, 0.85)),
            leaves=((0.30, 90, -2.0), (0.95, 84, -1.6))),
    ),
)


def build():
    return build_orb(SPEC)
