"""Ordgarius magnificus: a trapeze under an arching branch, one bolas, spindle egg sacs."""

import math

from spun.snares import BolasParameters, bolas

# The branch arches over the stage; the trapeze is its 45 mm chord, and the
# brown spindles hang from the branch beyond it.
SPEC = BolasParameters(
    id="magnificent-spider", width=1600, height=1200, mm_per_px=0.15, duration=12,
    branch=((230, 1000), (540, 600), (740, 230), (840, 170), (940, 230), (1140, 600), (1400, 960)),
    leaves=((0.02, 92, 2.5), (0.97, 96, 1.2), (0.62, 80, -1.4)),
    trapeze_mm=45, hang_x=0.42, hang_px=40, bolas_px=265, sticky_px=26,
    sacs=((480, 24, 124, 0.06), (1150, 26, 132, -0.04), (1262, 40, 116, -0.10)),
)


def build():
    return bolas(SPEC)
