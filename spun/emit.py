"""Replay the fully known plan topology into frozen, quantized .silk records."""

import colorsys
import math

import numpy as np

from .kinds import BY_NAME, COLORS, BUILDER_SHIFT, ENV, INVISIBLE, STICKY
from .silkfile import BEAD_DTYPE, NEVER, RECORD_DTYPE, quantize_coord, quantize_width


def _color(hexcode):
    return tuple(bytes.fromhex(hexcode[1:]))


def _style(thread, a, b, segment_index):
    if thread.styles is not None:
        width, color, alpha = thread.styles[min(segment_index, len(thread.styles)-1)]
    else:
        kind = BY_NAME[thread.kind]
        color = _color(COLORS["sticky"] if thread.sticky or kind.flags & STICKY else COLORS["dry"])
        if thread.kind == "AUX":
            color = _color(COLORS["dry"])
        width, alpha = kind.width, kind.alpha
        if thread.kind == "CAPTURE":
            angle = math.atan2(b[1]-a[1], b[0]-a[0])
            light = -math.pi/4
            amount = 0.22*abs(math.sin(angle-light))**4
            hue = (0.62+0.9*((angle-light) % math.pi)/math.pi) % 1
            spectral = colorsys.hsv_to_rgb(hue, 0.55, 1)
            color = tuple(round((1-amount)*base + amount*255*accent)
                          for base, accent in zip(color, spectral))
    return quantize_width(width or 0), color, round(255*alpha)


def emit(graph):
    """Node coordinates are quantized once, then reused by every owning thread."""
    coordinates = [(quantize_coord(node.point[0]), quantize_coord(node.point[1]))
                   for node in graph.nodes]
    rows = []
    thread_records = {}
    rest = {}

    def append(a, b, thread, builder, *, walking=False, segment_index=0):
        x0, y0 = coordinates[a]
        x1, y1 = coordinates[b]
        if x0 == x1 and y0 == y1:
            raise ValueError("relaxation collapsed an emitted sub-record")
        width, color, alpha = (0, (0, 0, 0), 0) if walking else _style(
            thread, graph.position(a), graph.position(b), segment_index)
        flags = builder << BUILDER_SHIFT
        if thread.env and not walking:
            flags |= ENV
        if thread.sticky and not walking:
            flags |= STICKY
        if walking:
            flags |= INVISIBLE
        rows.append((x0, y0, x1, y1, NEVER, BY_NAME["WALK" if walking else thread.kind].id,
                     width, *color, 255 if thread.kind != "AUX" else 128, flags, alpha))
        return len(rows)-1

    for action in graph.actions:
        if action.operation == "spin":
            thread_id = action.payload
            thread = graph.threads[thread_id]
            indices = []
            for j, (a, b) in enumerate(zip(thread.path, thread.path[1:])):
                indices.append(append(a, b, thread, action.builder, segment_index=j))
            thread_records[thread_id] = indices
        elif action.operation == "walk":
            for thread_id, start, end in action.payload:
                thread = graph.threads[thread_id]
                path = graph.final_subpath(thread_id, start, end)
                for a, b in zip(path, path[1:]):
                    append(a, b, thread, action.builder, walking=True)
        elif action.operation == "remove":
            for thread_id in action.payload:
                for index in thread_records[thread_id]:
                    rows[index] = (*rows[index][:4], len(rows), *rows[index][5:])
        elif action.operation == "rest":
            node, pose, angle = action.payload
            rest[action.builder] = {"x": coordinates[node][0]/4,
                                    "y": coordinates[node][1]/4,
                                    "angle": angle, "pose": pose}
        else:
            raise ValueError(f"unknown graph action {action.operation}")
    return np.array(rows, dtype=RECORD_DTYPE), np.zeros(0, dtype=BEAD_DTYPE), rest
