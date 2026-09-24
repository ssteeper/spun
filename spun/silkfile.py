"""Exact little-endian .silk v1 layouts and bounded quantization."""

from dataclasses import dataclass
from pathlib import Path
import math
import struct

import numpy as np

HEADER = struct.Struct("<4sHHHHIIHHHBBB3x")
HEADER_SIZE = HEADER.size
RECORD_DTYPE = np.dtype([
    ("x0", "<u2"), ("y0", "<u2"), ("x1", "<u2"), ("y1", "<u2"),
    ("death", "<u4"), ("kind", "u1"), ("width", "u1"),
    ("r", "u1"), ("g", "u1"), ("b", "u1"), ("lod", "u1"),
    ("flags", "u1"), ("alpha", "u1"),
], align=False)
BEAD_DTYPE = np.dtype([
    ("host", "<u4"), ("t", "<u2"), ("radius", "u1"), ("flags", "u1"),
], align=False)
RECORD_SIZE = RECORD_DTYPE.itemsize
BEAD_SIZE = BEAD_DTYPE.itemsize
COORD_SCALE = 4
WIDTH_SCALE = 32
NEVER = 0xFFFFFFFF
assert (HEADER_SIZE, RECORD_SIZE, BEAD_SIZE) == (32, 20, 8)


@dataclass(frozen=True)
class SilkFile:
    width: int
    height: int
    builder_count: int
    records: np.ndarray
    beads: np.ndarray
    data: bytes


def _quantize(value: float, scale: int, maximum: int) -> int:
    if not math.isfinite(value) or value < 0 or value * scale > maximum + 0.5:
        raise ValueError(f"value {value} cannot fit unsigned quantization")
    result = round(value * scale)
    if result > maximum:
        raise ValueError(f"value {value} cannot fit unsigned quantization")
    return result


def quantize_coord(px: float) -> int:
    return _quantize(px, COORD_SCALE, 0xFFFF)


def quantize_width(px: float) -> int:
    return _quantize(px, WIDTH_SCALE, 0xFF)


def quantize_t(fraction: float) -> int:
    return _quantize(fraction, 0xFFFF, 0xFFFF)


def quantize_radius(px: float) -> int:
    return _quantize(px, 16, 0xFF)


def _check_array(array: np.ndarray, dtype: np.dtype, name: str) -> None:
    if not isinstance(array, np.ndarray) or array.dtype != dtype or array.ndim != 1:
        raise TypeError(f"{name} must be a one-dimensional array with exact {dtype} layout")


def write_silk(width: int, height: int, builder_count: int,
               records: np.ndarray, beads: np.ndarray) -> bytes:
    """Serialize the GPU-ready arrays unchanged; caller validates semantics."""
    _check_array(records, RECORD_DTYPE, "records")
    _check_array(beads, BEAD_DTYPE, "beads")
    if not (1 <= width <= 0xFFFF and 1 <= height <= 0xFFFF):
        raise ValueError("canvas dimensions must fit unsigned 16-bit fields")
    if not (1 <= builder_count <= 3):
        raise ValueError("builder count must be between 1 and 3")
    if len(records) > 0xFFFFFFFF or len(beads) > 0xFFFFFFFF:
        raise ValueError("record or bead count exceeds unsigned 32-bit capacity")
    header = HEADER.pack(b"SILK", 1, HEADER_SIZE, RECORD_SIZE, BEAD_SIZE,
                         len(records), len(beads), width, height,
                         COORD_SCALE, WIDTH_SCALE, 0, builder_count)
    return header + records.tobytes() + beads.tobytes()


def read_silk(source: bytes | bytearray | memoryview | Path) -> SilkFile:
    """Decode exact file boundaries; reject non-v1, truncated or trailing data."""
    data = Path(source).read_bytes() if isinstance(source, Path) else bytes(source)
    if len(data) < HEADER_SIZE:
        raise ValueError("truncated .silk header")
    (magic, version, header_size, record_size, bead_size, count, bead_count,
     width, height, scale, width_scale, flags, builders) = HEADER.unpack_from(data)
    if (magic, version, header_size, record_size, bead_size, scale,
            width_scale, flags) != (b"SILK", 1, 32, 20, 8, 4, 32, 0):
        raise ValueError("invalid .silk v1 header")
    if data[29:32] != b"\0\0\0" or width == 0 or height == 0 or not 1 <= builders <= 3:
        raise ValueError("invalid .silk canvas, builders or reserved bytes")
    if len(data) != HEADER_SIZE + count * RECORD_SIZE + bead_count * BEAD_SIZE:
        raise ValueError(".silk length differs from declared record and bead counts")
    records = np.frombuffer(data, dtype=RECORD_DTYPE, count=count, offset=HEADER_SIZE)
    beads = np.frombuffer(data, dtype=BEAD_DTYPE, count=bead_count,
                          offset=HEADER_SIZE + count * RECORD_SIZE)
    return SilkFile(width, height, builders, records, beads, data)
