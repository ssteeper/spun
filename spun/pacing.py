"""Silk-length pacing, environmental compression and presentation-time easing."""

import math

import numpy as np

from .kinds import ENV, KINDS

_PROFILE = ((0.0, 0.55), (0.08, 1.0), (0.88, 1.0), (1.0, 0.45))


def _presentation_time(u):
    """Integrate inverse piecewise-linear speed exactly over raw-time fraction."""
    total = 0.0
    for (lo, speed0), (hi, speed1) in zip(_PROFILE, _PROFILE[1:]):
        if u <= lo:
            break
        span = min(u, hi) - lo
        slope = (speed1 - speed0)/(hi - lo)
        total += math.log1p(slope*span/speed0)/slope if abs(slope) > 1e-12 else span/speed0
    return total


def pace(records, duration_seconds):
    coords = np.column_stack((records["x1"].astype(float)-records["x0"],
                              records["y1"].astype(float)-records["y0"]))
    distances = np.linalg.norm(coords, axis=1)/4
    lengths = np.array([distances[i]/KINDS[int(k)].speed + KINDS[int(k)].dwell
                        for i, k in enumerate(records["kind"])], dtype=float)
    env = (records["flags"] & ENV) != 0
    def prepared(factor):
        raw = np.where(env, lengths*factor, lengths)
        endpoints = np.r_[0, np.cumsum(raw)]
        u = endpoints/endpoints[-1]
        times = np.fromiter((_presentation_time(float(v)) for v in u), float, len(u))
        times /= times[-1]
        return times
    factor = 1.0
    times = prepared(factor)
    while np.sum(np.diff(times)[env]) > 0.08:
        factor *= 0.5
        times = prepared(factor)
    samples = np.interp(np.linspace(0, 1, 512), times, np.arange(len(records)+1, dtype=float))
    samples[0], samples[-1] = 0, len(records)
    stages = []
    for i, kind in enumerate(records["kind"]):
        label = KINDS[int(kind)].label
        if label is not None and (not stages or stages[-1]["label"] != label):
            stages.append({"label": label, "start": i})
    stages.append({"label": "at rest", "start": len(records)})
    return {"durationSeconds": duration_seconds,
            "timeline": [round(float(value), 3) for value in samples],
            "stages": stages, "envFraction": float(np.sum(np.diff(times)[env]))}
