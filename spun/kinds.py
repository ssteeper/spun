"""The single source of construction-kind timing and appearance defaults."""

from dataclasses import dataclass

STICKY = 1
ENV = 2
INVISIBLE = 4
BUILDER_SHIFT = 4
BUILDER_MASK = 0x30
SATELLITE = 1
GLUE = 2
LURE = 4


@dataclass(frozen=True)
class Kind:
    id: int
    name: str
    label: str | None
    speed: float
    dwell: float
    width: float | None
    alpha: float
    flags: int = 0
    width_end: float | None = None
    alpha_max: float | None = None
    sticky_part: str | None = None


KINDS = (
    Kind(0, "SCAFFOLD", "scaffold", 900, 0, 7, 1.0, ENV, width_end=2),
    Kind(1, "LEAF", "hauling a leaf", 900, 0, 1.1, 1.0, ENV),
    Kind(2, "BRIDGE", "bridge line", 220, 0.25, 1.4, 0.9),
    Kind(3, "FRAME", "framing", 260, 0.10, 1.3, 0.9),
    Kind(4, "RADIUS", "laying radii", 320, 0.05, 0.9, 0.85),
    Kind(5, "HUB", "hub", 120, 0.02, 0.7, 0.8),
    Kind(6, "AUX", "temporary spiral", 380, 0.02, 0.6, 0.55),
    Kind(7, "CAPTURE", "capture spiral", 150, 0.035, 0.75, 0.9, STICKY),
    Kind(8, "STABILIMENTUM", "weaving the cross", 60, 0.01, 1.9, 1.0),
    Kind(9, "TUFT", "tufting the lines", 80, 0.02, 0.9, 0.9),
    Kind(10, "EGGSAC", "egg sacs", 90, 0.02, 1.0, 1.0),
    Kind(11, "TANGLE", "tangle", 240, 0.05, 0.6, 0.35, alpha_max=0.6),
    Kind(12, "RETREAT", "retreat", 110, 0.01, 0.6, 0.6),
    Kind(13, "GUMFOOT", "gumfoot lines", 200, 0.10, 0.7, 0.85, sticky_part="bottom"),
    Kind(14, "CRIBELLATE", "combing the net", 70, 0.01, 0.8, 0.55),
    Kind(15, "BOLAS", "the bolas", 90, 0.30, 0.8, 0.9, sticky_part="last"),
    Kind(16, "WALK", None, 520, 0, None, 0, INVISIBLE),
)

BY_NAME = {kind.name: kind for kind in KINDS}

COLORS = {
    "dry": "#cdd6e4", "sticky": "#eaf0f8", "stabilimentum": "#f6f9ff",
    "tuft": "#ffffff", "cribellate": "#dce6ff", "retreat": "#dfe4ea",
    "bolas": "#efe6c8", "eggsac_arachnura": "#b8955a",
    "eggsac_ordgarius": "#7a5334", "leaf": "#9c7a4c",
    "leaf_vein": "#6e5234", "golden_frame": "#c9a24e",
    "golden_radius": "#d7b25c", "golden_capture": "#f0cf73",
    "golden_aux": "#b89a55",
}
