"""Tension-only dynamic relaxation with deterministic acceptance and fallback."""

from dataclasses import dataclass

import numpy as np

from .silkfile import quantize_coord
from .validate import _crossing_pairs, _intersects

_ELASTIC = {"FRAME": (0.03, 1.0), "BRIDGE": (0.03, 1.0),
            "RADIUS": (0.02, 1.0), "CAPTURE": (0.01, 0.15),
            "HUB": (0.01, 0.3)}


@dataclass(frozen=True)
class Relaxation:
    iterations: int
    max_displacement: float
    accepted: bool
    reason: str
    converged: bool
    final_step: float


def _final_lines(graph, points):
    lines = []
    for thread in graph.threads:
        if not thread.live or thread.kind not in _ELASTIC:
            continue
        for a, b in zip(thread.path, thread.path[1:]):
            first = tuple(quantize_coord(float(v)) for v in points[a])
            second = tuple(quantize_coord(float(v)) for v in points[b])
            lines.append((len(lines), first, second, thread.kind == "RADIUS"))
    return lines


def _new_crossing(graph, planned, candidate):
    planned_lines = _final_lines(graph, planned)
    final_lines = _final_lines(graph, candidate)
    for (i, a, b, _), (j, c, d, _) in _crossing_pairs(final_lines):
        if not _intersects(a, b, c, d):
            continue
        shared = {a, b} & {c, d}
        if shared and len(shared) == 1:
            point = next(iter(shared))
            u = b if a == point else a
            v = d if c == point else c
            if ((u[0]-point[0])*(v[0]-point[0]) +
                    (u[1]-point[1])*(v[1]-point[1])) <= 0 or (
                        (u[0]-point[0])*(v[1]-point[1]) -
                        (u[1]-point[1])*(v[0]-point[0])) != 0:
                continue
        _, p, q, _ = planned_lines[i]
        _, r, s, _ = planned_lines[j]
        if not _intersects(p, q, r, s):
            return True
    return False


def relax(graph, radial_paths, mean_radius):
    original = np.asarray([node.point for node in graph.nodes], dtype=float)
    fixed = np.asarray([node.fixed for node in graph.nodes])
    edges = []
    for thread in graph.threads:
        if thread.live and thread.kind in _ELASTIC:
            epsilon, stiffness = _ELASTIC[thread.kind]
            edges.extend((a, b, epsilon, stiffness)
                         for a, b in zip(thread.path, thread.path[1:]))
    if not edges:
        raise ValueError("relaxation needs an orb's surviving structural network")
    starts = np.array([e[0] for e in edges], dtype=np.intp)
    ends = np.array([e[1] for e in edges], dtype=np.intp)
    epsilon = np.array([e[2] for e in edges])
    stiffness = np.array([e[3] for e in edges])
    l0 = np.linalg.norm(original[ends]-original[starts], axis=1)*(1-epsilon)
    position = original.copy()
    velocity = np.zeros_like(position)
    iterations = 0
    final_step = 0.0
    for iterations in range(1, 401):
        vectors = position[ends]-position[starts]
        distances = np.linalg.norm(vectors, axis=1)
        tension = stiffness*np.maximum(distances-l0, 0.0)/np.maximum(distances, 1e-12)
        force = np.zeros_like(position)
        contribution = vectors*tension[:, None]
        np.add.at(force, starts, contribution)
        np.add.at(force, ends, -contribution)
        velocity = 0.85*(velocity+0.2*force)
        velocity[fixed] = 0
        change = 0.2*velocity
        position += change
        final_step = float(np.max(np.linalg.norm(change, axis=1)))
        if final_step < 1e-3:
            break
    max_shift = float(np.max(np.linalg.norm(position-original, axis=1)))
    reason = "accepted"
    if max_shift > 0.03*mean_radius:
        reason = "displacement exceeds three percent of mean radius"
    elif any(any(float(np.dot(position[b]-position[a], original[path[-1]]-original[path[0]])) <= 0
                     for a, b in zip(path, path[1:])) for path in radial_paths):
        reason = "junction order reversed along a radius"
    elif bool(np.any(np.all(np.rint(position[starts]*4) == np.rint(position[ends]*4), axis=1))):
        reason = "quantization collapsed a silk segment"
    elif _new_crossing(graph, original, position):
        reason = "new crossing in surviving network"
    if reason == "accepted":
        # Tufts ride on the frame: their free interior follows the mean shift of
        # the two frame knots they hang from, so a tuft keeps its shape and length.
        for thread in graph.threads:
            if thread.kind == "TUFT":
                shift = (position[thread.path[0]]-original[thread.path[0]] +
                         position[thread.path[-1]]-original[thread.path[-1]])/2
                for node in thread.path[1:-1]:
                    if not fixed[node]:
                        position[node] = original[node]+shift
        for node, point in zip(graph.nodes, position):
            node.point = (float(point[0]), float(point[1]))
    # Rejected equilibrium leaves *all* nodes at their original planned locations.
    return Relaxation(iterations, max_shift, reason == "accepted", reason,
                      final_step < 1e-3, final_step)
