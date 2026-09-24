"""Reproducible Rayleigh–Plateau droplets on surviving silk, and visible glue."""

import logging
import math
import zlib

import numpy as np

from .kinds import BUILDER_MASK, ENV, GLUE, INVISIBLE, LURE, SATELLITE, STICKY, BY_NAME
from .silkfile import BEAD_DTYPE, NEVER, quantize_radius, quantize_t

_LOG = logging.getLogger(__name__)
_MAX_BEADS = 32000


def coating_radius(r0, rng):
    """Thread-wide lognormal coating radius, with median r0 and sigma 0.18."""
    return float(rng.lognormal(math.log(r0), .18))


def spacing(radius, rng):
    """Fastest-growing wavelength with independent ±10% spacing jitter."""
    return 2 * math.pi * math.sqrt(2) * radius * float(rng.uniform(.9, 1.1))


def primary_radius(radius, wavelength):
    return (3 * (radius*radius - (.3*radius)**2) * wavelength / 4)**(1/3)


def _resolve(chain, lengths, distance):
    """Map arclength to the host record; a shared junction belongs to the next."""
    offset = 0.
    for host, length in zip(chain, lengths):
        if distance < offset + length or host == chain[-1]:
            return host, quantize_t(min(1., max(0., (distance-offset)/length)))
        offset += length
    raise AssertionError("arclength outside thread")


def generate(records: np.ndarray, species_id: str, r0: float) -> np.ndarray:
    """Return BEAD_DTYPE sorted by host/t; seed is independent from construction RNG.

    A thread is a maximal consecutive same-kind/builder/adhesivity chain, whose
    adjacent records touch. Temporary (ever-dying) hosts are deliberately bare.
    """
    rng = np.random.default_rng(zlib.crc32(species_id.encode("utf-8")) ^ 0xB34D5)
    kind = BY_NAME
    groups = []
    chain = []
    dying = 0
    for i, row in enumerate(records):
        flags = int(row["flags"])
        eligible = not flags & (ENV | INVISIBLE) and int(row["death"]) == NEVER
        if not eligible:
            if chain:
                groups.append(chain)
                chain = []
            dying += int(int(row["death"]) != NEVER and not flags & (ENV | INVISIBLE))
            continue
        previous = records[chain[-1]] if chain else None
        touching = previous is not None and int(previous["x1"]) == int(row["x0"]) and int(previous["y1"]) == int(row["y0"])
        same_style = (previous is not None and int(previous["kind"]) == int(row["kind"])
                      and (int(previous["flags"]) & (BUILDER_MASK | STICKY)) == (flags & (BUILDER_MASK | STICKY)))
        if chain and not (touching and same_style):
            groups.append(chain)
            chain = []
        chain.append(i)
    if chain:
        groups.append(chain)
    if dying:
        _LOG.info("%s: skipped %d ever-dying bead hosts", species_id, dying)

    # Each entry is an indivisible primary and optional satellite. Glue is
    # reserved before any thinning, so a tight budget cannot remove a lure.
    primaries = []
    glue = []
    for chain in groups:
        row = records[chain[0]]
        adhesive = bool(int(row["flags"]) & STICKY)
        if int(row["kind"]) == kind["BOLAS"].id and adhesive:
            host = chain[-1]
            glue.append([(host,65535,quantize_radius(8.5),GLUE | LURE)])
            continue
        lengths = [math.hypot(int(records[h]["x1"])-int(records[h]["x0"]),
                              int(records[h]["y1"])-int(records[h]["y0"]))/4 for h in chain]
        total = sum(lengths)
        if int(row["kind"]) == kind["GUMFOOT"].id and adhesive:
            # Several drops on each glue-bearing bottom; never ordinary dew.
            step = max(4., 2*math.pi*math.sqrt(2)*r0*.75)
            for distance in np.arange(step/2,total,step):
                host,t = _resolve(chain,lengths,float(distance))
                glue.append([(host,t,quantize_radius(min(15.9,max(.9,1.6*r0))),GLUE)])
            continue
        radius = coating_radius(r0,rng) * (1.0 if adhesive else .8)
        step = spacing(radius,rng) / (1.0 if adhesive else .15)
        distance = step/2
        previous_distance = None
        while distance < total:
            host,t = _resolve(chain,lengths,distance)
            wavelength = spacing(radius,rng) if adhesive else step
            bead_radius = primary_radius(radius,wavelength)
            group = [(host,t,quantize_radius(min(15.9,bead_radius)),0)]
            if previous_distance is not None and rng.random() < .7:
                sat_host,sat_t = _resolve(chain,lengths,(previous_distance+distance)/2)
                group.append((sat_host,sat_t,quantize_radius(min(15.9,.28*bead_radius)),SATELLITE))
            primaries.append(group)
            previous_distance = distance
            distance += spacing(radius,rng) / (1.0 if adhesive else .15)
    glue_count = sum(len(group) for group in glue)
    if glue_count > _MAX_BEADS:
        raise ValueError(f"{species_id}: glue alone exceeds {_MAX_BEADS} bead budget")
    count = glue_count + sum(len(group) for group in primaries)
    if count > _MAX_BEADS:
        # Reproducible hash priority, independent of platform RNG and dict order.
        ranked = sorted(range(len(primaries)), key=lambda i:
                        (zlib.crc32(f"{species_id}:{i}".encode("utf-8")), i))
        keep = set()
        budget = _MAX_BEADS-glue_count
        for index in ranked:
            size = len(primaries[index])
            if budget >= size:
                budget -= size
                keep.add(index)
        primaries = [group for i,group in enumerate(primaries) if i in keep]
        _LOG.info("%s: thinned %d beads to budget", species_id, count-_MAX_BEADS)
    beads = [bead for group in (*primaries,*glue) for bead in group]
    beads.sort(key=lambda bead:(bead[0],bead[1],bead[3] & SATELLITE))
    return np.array(beads,dtype=BEAD_DTYPE)
