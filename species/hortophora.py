"""Hortophora transmarina: the dusk-built reference orb."""

from spun.orb import OrbParameters, build_orb

SPEC = OrbParameters(
    id="garden-orb-weaver", width=1200, height=1600,
    polygon=((185, 285), (1010, 305), (940, 545), (1050, 990),
             (620, 1420), (190, 1260), (250, 910), (175, 570)),
    radii_min=20, radii_max=24, hub_fraction=0.42,
    spacing_outer=14, spacing_inner=11, free_radius=76,
    auxiliary_spacing=42, mm_per_px=0.6, duration=28,
)


def build():
    return build_orb(SPEC)
