"""Hortophora transmarina: the dusk-built reference orb."""

from spun.orb import OrbParameters, build_orb
from spun.scaffold import BranchSpec, frame_polygon

# A garden shrub: three stems rise from one base; the orb fills the space
# they enclose, its corners tied to the bark or to short side twigs.
BRANCHES = (
    BranchSpec(
        controls=((540, 1600), (318, 1325), (190, 1140), (120, 900), (115, 640),
                  (190, 400), (330, 250)),
        anchors=((6, (318, 1325)), (7, (157, 1040)), (8, (136, 766)), (9, (166, 515)),
                 (0, (346, 331))),
        leaves=((0.97, 90, -1.2), (0.62, 86, 3.4))),
    BranchSpec(
        controls=((620, 1600), (679, 1424), (850, 1290), (993, 1179), (1060, 1100)),
        anchors=((5, (679, 1424)), (4, (993, 1179))),
        leaves=((0.96, 80, -0.6),)),
    BranchSpec(
        controls=((650, 1600), (900, 1500), (1120, 1250), (1100, 900), (1085, 560),
                  (980, 400), (800, 330)),
        anchors=((3, (1055, 855)), (2, (1049, 546)), (1, (781, 361))),
        leaves=((0.30, 95, 0.2), (0.97, 88, -2.6), (0.62, 84, 0.1))),
)

SPEC = OrbParameters(
    id="garden-orb-weaver", width=1200, height=1600,
    polygon=frame_polygon(BRANCHES),
    radii_min=17, radii_max=21, hub_fraction=0.40,
    spacing_outer=14, spacing_inner=11, free_radius=70,
    auxiliary_spacing=42, mm_per_px=0.6, duration=28,
    lower_anchor=5,
    branches=BRANCHES,
)


def build():
    return build_orb(SPEC)
