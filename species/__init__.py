"""Species registry: catalogue facts (§3, §4.12) plus each module's ``build()``."""

from dataclasses import dataclass
from typing import Callable

from . import (arachnura, argiope, austracantha, deinopis, golden, hortophora, latrodectus,
               ordgarius, phonognatha)


@dataclass(frozen=True)
class Species:
    id: str
    stem: str
    name: str
    scientific: str
    kind: str
    mm_per_px: float
    duration: float
    r0: float
    body_mm: float
    body_scale: float
    pose: str
    build: Callable


CATALOGUE = (
    Species("golden-orb-weaver", "golden", "Golden Orb-weaver", "Trichonephila edulis",
            "orb", 0.8, 42, 0.85, 30, 1.6, "head-down", golden.build),
    Species("st-andrews-cross", "argiope", "St Andrew's Cross Spider", "Argiope keyserlingi",
            "orb", 0.5, 30, 0.9, 15, 1.8, "hub-x", argiope.build),
    Species("garden-orb-weaver", "hortophora", "Garden Orb-weaver", "Hortophora transmarina",
            "orb", 0.6, 28, 1.0, 22, 1.6, "hub-rest", hortophora.build),
    Species("leaf-curling-spider", "phonognatha", "Leaf-curling Spider", "Phonognatha graeffei",
            "orb", 0.45, 30, 0.9, 12, 1.8, "in-leaf", phonognatha.build),
    Species("christmas-jewel-spider", "austracantha", "Christmas Jewel Spider",
            "Austracantha minax", "orb", 0.35, 36, 0.8, 8, 2.0, "hub-rest", austracantha.build),
    Species("scorpion-tailed-spider", "arachnura", "Scorpion-tailed Spider", "Arachnura higginsi",
            "orb", 0.35, 26, 0.85, 16, 1.6, "hub-tail", arachnura.build),
    Species("net-casting-spider", "deinopis", "Net-casting Spider", "Deinopis subrufa",
            "snare", 0.12, 18, 0.7, 25, 1.0, "net", deinopis.build),
    Species("magnificent-spider", "ordgarius", "Magnificent Spider", "Ordgarius magnificus",
            "snare", 0.15, 12, 0.8, 14, 1.0, "hanging", ordgarius.build),
    Species("redback-spider", "latrodectus", "Redback Spider", "Latrodectus hasselti",
            "snare", 0.3, 24, 1.1, 10, 1.8, "retreat", latrodectus.build),
)
BY_ID = {species.id: species for species in CATALOGUE}
# id -> build(); each build() stays a module function, so ``__module__`` names the stem.
SPECIES = {species.id: species.build for species in CATALOGUE}
