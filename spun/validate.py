"""Validate a decoded specimen and its small, construction-derived metadata.

Metadata schema: kind ('orb'|'snare'), golden (bool), orbs (list of
{builder, hub:[x,y], frame:[[x,y],...], radii:[[x,y],...],
openSectors:[[startRadians,endRadians],...]}), timeline (512 cursors),
stages ([{label,start}]), rests ({builderIndex:[x,y]}),
catalogueBytes, indexBytes, defaultBytes (byte totals). Coordinates in
metadata are native px; validation compares against quantized silk geometry.
"""

from collections import defaultdict
import math
from pathlib import Path

import numpy as np

from .kinds import BY_NAME, BUILDER_MASK, BUILDER_SHIFT, ENV, GLUE, INVISIBLE, KINDS, STICKY
from .silkfile import NEVER, SilkFile, read_silk


class ValidationError(ValueError):
    def __init__(self, rule: int, message: str):
        self.rule = rule
        super().__init__(f"Rule {rule}: {message}")


def _require(condition: bool, rule: int, message: str) -> None:
    if not condition:
        raise ValidationError(rule, message)


def _point(point: object) -> tuple[int, int]:
    return tuple(round(float(v) * 4) for v in point)  # type: ignore[return-value]


def _endpoints(row: np.void) -> tuple[tuple[int, int], tuple[int, int]]:
    return ((int(row["x0"]), int(row["y0"])),
            (int(row["x1"]), int(row["y1"])))


def _cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return ((b[0] - a[0]) * (c[1] - a[1]) -
            (b[1] - a[1]) * (c[0] - a[0]))


def _intersects(a, b, c, d) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ab_c == ab_d == cd_a == cd_b == 0:
        return max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
    return ab_c * ab_d <= 0 and cd_a * cd_b <= 0


def _inside(h, polygon) -> bool:
    x, y = h
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if _cross(a, b, h) == 0 and min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
            return False
        if (a[1] > y) != (b[1] > y):
            if x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
    return inside


def _cv(values: list[float]) -> float:
    return float(np.std(values) / np.mean(values)) if len(values) >= 2 and np.mean(values) > 0 else float("nan")


def _crossing_pairs(lines: list[tuple[int, tuple[int, int], tuple[int, int], bool]]):
    """Spatial bins avoid the quadratic all-chords comparison for dense orbs."""
    bins: dict[tuple[int, int], list[int]] = defaultdict(list)
    for n, (_, a, b, _) in enumerate(lines):
        for x in range(min(a[0], b[0]) // 128, max(a[0], b[0]) // 128 + 1):
            for y in range(min(a[1], b[1]) // 128, max(a[1], b[1]) // 128 + 1):
                bins[x, y].append(n)
    seen: set[tuple[int, int]] = set()
    for indices in bins.values():
        for offset, left in enumerate(indices):
            for right in indices[offset + 1:]:
                pair = (left, right)
                if pair not in seen:
                    seen.add(pair)
                    yield lines[left], lines[right]


def _orb_geometry(rows: np.ndarray, orb: dict, golden: bool) -> None:
    builder = int(orb["builder"])
    hub = _point(orb["hub"])
    polygon = [_point(point) for point in orb["frame"]]
    rays = [_point(point) for point in orb["radii"]]
    _require(len(polygon) >= 3 and _inside(hub, polygon), 5, "hub must lie strictly inside the frame polygon")
    _require(len(rays) >= 3 and len(set(rays)) == len(rays), 5, "orb needs distinct radial endpoints")
    radial = [(i, *_endpoints(r)) for i, r in enumerate(rows)
              if r["kind"] == BY_NAME["RADIUS"].id and
              (int(r["flags"]) & BUILDER_MASK) >> BUILDER_SHIFT == builder and
              int(r["death"]) == NEVER]
    captures = [(i, *_endpoints(r)) for i, r in enumerate(rows)
                if r["kind"] == BY_NAME["CAPTURE"].id and
                (int(r["flags"]) & BUILDER_MASK) >> BUILDER_SHIFT == builder and
                int(r["death"]) == NEVER]
    _require(bool(radial) and bool(captures), 5, "orb must have live radius and capture records")
    ray_angles = [math.atan2(y - hub[1], x - hub[0]) % math.tau for x, y in rays]
    order = sorted(range(len(rays)), key=ray_angles.__getitem__)
    positions = {j: position for position, j in enumerate(order)}
    angles = [ray_angles[j] for j in order]
    gaps = [(angles[(i + 1) % len(angles)] - angle) % math.tau
            for i, angle in enumerate(angles)]
    _require(all(gap > 0 for gap in gaps), 5, "rays must have distinct angles")
    _require(0.08 <= _cv(gaps) <= 0.40, 6, "adjacent radial-gap CV must be 0.08–0.40")
    distances: dict[int, list[float]] = defaultdict(list)
    adjacency: dict[tuple[int, int], list[tuple[tuple[int, int], int]]] = defaultdict(list)
    for i, a, b in radial:
        adjacency[a].append((b, i))
        adjacency[b].append((a, i))
    spokes: dict[tuple[int, int], int] = {}
    visited: set[int] = set()
    deviation = 0.03 * float(np.mean([math.dist(hub, end) for end in rays])) + 2
    for j, foot in enumerate(rays):
        _require(foot in adjacency, 5, "declared radial endpoint is not on silk")
        point = foot
        previous = None
        while point != hub:
            _require(point not in spokes or spokes[point] == j, 5, "radial spokes merge away from hub")
            spokes[point] = j
            following = [(next_point, index) for next_point, index in adjacency[point]
                         if next_point != previous]
            _require(len(following) == 1, 5, "radial spoke is broken, forked or cyclic")
            next_point, record_index = following[0]
            _require(record_index not in visited, 5, "radial record belongs to more than one spoke")
            visited.add(record_index)
            ex, ey = foot[0]-hub[0], foot[1]-hub[1]
            span = math.hypot(ex, ey)
            _require(abs(_cross(hub, foot, point))/span <= deviation and
                     ((point[0]-hub[0])*ex+(point[1]-hub[1])*ey) >= 0,
                     5, "relaxed spoke exceeds the allowed displacement")
            previous, point = point, next_point
    _require(len(visited) == len(radial), 5, "unclaimed surviving radial segment")

    def ray_for(point: tuple[int, int]) -> tuple[int, float]:
        _require(point != hub and point in spokes, 5, "capture junction must coincide with a radial node")
        return spokes[point], math.dist(point, hub)/4

    for _, a, b in captures:
        ja, da = ray_for(a)
        jb, db = ray_for(b)
        _require(ja != jb, 5, "capture chord must join distinct radii")
        distances[ja].append(da)
        distances[jb].append(db)
        for start, end in orb.get("openSectors", []):
            for point in (a, b, ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)):
                theta = math.atan2(point[1] - hub[1], point[0] - hub[0]) % math.tau
                _require(not 0 < (theta - start) % math.tau < (end - start) % math.tau,
                         5, "capture chord spans an open sector")
    for j, values in distances.items():
        ordered = sorted(values)
        distinct = [ordered[0]]
        for value in ordered[1:]:
            if value - distinct[-1] > 0.26:
                distinct.append(value)
        distances[j] = distinct
    spacings = [b - a for values in distances.values() for a, b in zip(values, values[1:])]
    _require(0.05 <= _cv(spacings) <= 0.35, 6, "capture-spacing CV must be 0.05–0.35")
    # Chords are laid inward; each spoke's first visit in a later row is closer to H.
    last_distance: dict[int, float] = {}
    direction = 0
    turnbacks = 0
    for _, a, b in captures:
        ja, da = ray_for(a)
        jb, db = ray_for(b)
        for j, d in ((ja, da), (jb, db)):
            _require(j not in last_distance or d <= last_distance[j] + 0.26,
                     5, "capture junctions must progress inward along each radius")
            last_distance[j] = d
        step = (positions[jb] - positions[ja]) % len(angles)
        sign = 1 if step == 1 else -1 if step == len(angles) - 1 else 0
        if sign and direction and sign != direction:
            turnbacks += 1
        if sign:
            direction = sign
    lines = [(i, a, b, True) for i, a, b in radial] + [(i, a, b, False) for i, a, b in captures]
    for first, second in _crossing_pairs(lines):
        i, a, b, radial_a = first
        j, c, d, radial_b = second
        if not _intersects(a, b, c, d):
            continue
        shared = {a, b} & {c, d}
        allowed = bool(shared) and not (_cross(a, b, c) == _cross(a, b, d) == 0)
        if len(shared) == 1 and _cross(a, b, c) == _cross(a, b, d) == 0:
            point = next(iter(shared))
            first_other = b if a == point else a
            second_other = d if c == point else c
            allowed = ((first_other[0]-point[0])*(second_other[0]-point[0]) +
                       (first_other[1]-point[1])*(second_other[1]-point[1])) <= 0
        _require(allowed, 5, f"forbidden final-web crossing between records {i} and {j}")
    if golden:
        ymin, ymax = min(p[1] for p in polygon), max(p[1] for p in polygon)
        _require((hub[1] - ymin) / (ymax - ymin) <= 0.4 and turnbacks >= 6,
                 6, "golden hub must be high and capture must turn back at least six times")


def validate(source: bytes | bytearray | memoryview | Path | SilkFile, metadata: dict) -> SilkFile:
    """Raise ValidationError with a stable Rule 1–9 identifier on first violation."""
    try:
        silk = source if isinstance(source, SilkFile) else read_silk(source)
        if isinstance(source, SilkFile):
            silk = read_silk(source.data)
    except (ValueError, TypeError) as exc:
        raise ValidationError(1, str(exc)) from exc
    rows, beads = silk.records, silk.beads
    count = len(rows)
    _require(bool(count), 1, "at least one record is required")
    _require(bool(np.all(rows["x0"] <= silk.width * 4) and np.all(rows["x1"] <= silk.width * 4) and
                  np.all(rows["y0"] <= silk.height * 4) and np.all(rows["y1"] <= silk.height * 4)),
             1, "record coordinates exceed canvas")
    _require(bool(np.all((rows["x0"].astype(np.int32) - rows["x1"].astype(np.int32)) ** 2 +
                         (rows["y0"].astype(np.int32) - rows["y1"].astype(np.int32)) ** 2 >= 1)),
             1, "zero-length record")
    _require(bool(np.all(rows["kind"] < len(BY_NAME)) and
                  np.all((rows["flags"] & (0xFF ^ (BUILDER_MASK | ENV | STICKY | INVISIBLE))) == 0) and
                  np.all(((rows["flags"] & BUILDER_MASK) >> BUILDER_SHIFT) < silk.builder_count)),
             1, "unknown kind, invalid flags or builder index")
    _require(bool(np.all((rows["kind"] == BY_NAME["WALK"].id) ==
                         ((rows["flags"] & INVISIBLE) != 0))),
             1, "only WALK records may be invisible")
    _require(bool(np.all(np.isin(rows["kind"][(rows["flags"] & ENV) != 0],
                                   [BY_NAME["SCAFFOLD"].id, BY_NAME["LEAF"].id])) and
                  np.all((rows["flags"][(rows["kind"] == BY_NAME["SCAFFOLD"].id) |
                                        (rows["kind"] == BY_NAME["LEAF"].id)] & ENV) != 0)),
             1, "ENV belongs only to scaffold and leaf records")
    last: dict[int, tuple[int, int]] = {}
    finished: set[int] = set()
    current: int | None = None
    live_nodes: set[tuple[int, int]] = set()
    for i, row in enumerate(rows):
        start, end = _endpoints(row)
        builder = (int(row["flags"]) & BUILDER_MASK) >> BUILDER_SHIFT
        if row["flags"] & ENV:
            live_nodes.update((start, end))
            continue
        if current != builder:
            _require(builder not in finished, 2, f"builder {builder} resumed after another builder")
            _require(builder == len(last), 2, "builders must start in index order")
            if current is not None:
                finished.add(current)
            current = builder
        _require(start == last[builder] if builder in last else start in live_nodes,
                 2, f"builder {builder} teleported at record {i} or began off the scaffold")
        last[builder] = end
        if not row["flags"] & INVISIBLE:
            live_nodes.add(end)
    _require(len(last) == silk.builder_count, 2, "builder has no records")
    live: dict[tuple[tuple[int, int], tuple[int, int]], list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        a, b = _endpoints(row)
        pair = tuple(sorted((a, b)))
        if row["kind"] == BY_NAME["WALK"].id:
            _require(any(death > i for death in live[pair]), 3,
                     f"WALK {i} does not retrace an earlier live visible record")
        elif not row["flags"] & INVISIBLE:
            live[pair].append(int(row["death"]))
    for i, row in enumerate(rows):
        death = int(row["death"])
        _require(death == NEVER or i < death < count, 4, f"invalid death index on record {i}")
        if metadata.get("kind") == "orb" and row["kind"] == BY_NAME["AUX"].id:
            _require((death == NEVER) == bool(metadata.get("golden", False)),
                     4, "all non-golden AUX must die; golden AUX must survive")
    _require(metadata.get("kind") in ("orb", "snare"), 5, "kind must be orb or snare")
    if metadata["kind"] == "orb":
        orbs = metadata.get("orbs", [])
        _require(len(orbs) == silk.builder_count, 5, "one orb geometry entry per builder is required")
        for orb in orbs:
            _orb_geometry(rows, orb, bool(metadata.get("golden", False)))
    _require(len(beads) <= 32000 and bool(np.all(beads["host"] < count)),
             7, "invalid bead host or bead budget")
    for i, bead in enumerate(beads):
        host = rows[int(bead["host"])]
        _require(not host["flags"] & ENV and host["kind"] != BY_NAME["WALK"].id and
                 (not bead["flags"] & GLUE or host["flags"] & STICKY),
                 7, f"bead {i} is attached to forbidden host")
        _require(not int(bead["flags"]) & ~7, 7, "unknown bead flags")
    _require(all((int(a["host"]), int(a["t"])) <= (int(b["host"]), int(b["t"]))
                 for a, b in zip(beads, beads[1:])), 7, "beads must be sorted by host and t")
    timeline = metadata.get("timeline", [])
    _require(len(timeline) == 512 and all(math.isfinite(x) and 0 <= x <= count for x in timeline) and
             timeline[0] == 0 and timeline[-1] == count and
             all(a <= b for a, b in zip(timeline, timeline[1:])),
             8, "timeline must have 512 ordered samples from zero to N")
    stages = metadata.get("stages", [])
    _require(bool(stages) and stages[-1] == {"label": "at rest", "start": count} and
             all(isinstance(s.get("label"), str) and isinstance(s.get("start"), int) and
                 0 <= s["start"] <= count for s in stages) and
             all(a["start"] <= b["start"] for a, b in zip(stages, stages[1:])),
             8, "stages must be ordered and end at rest at N")
    expected_stages = []
    for i, row in enumerate(rows):
        label = KINDS[int(row["kind"])].label
        if label is not None and (not expected_stages or expected_stages[-1]["label"] != label):
            expected_stages.append({"label": label, "start": i})
    expected_stages.append({"label": "at rest", "start": count})
    _require(stages == expected_stages, 8, "stage labels must match every record-kind status change")
    rests = metadata.get("rests", {})
    _require(len(rests) == silk.builder_count and
             all(_point(rests[b]) == last[b] for b in range(silk.builder_count)),
             8, "every builder must end at her stated spinneret rest point")
    _require(len(silk.data) <= 640 * 1024 and
             isinstance(metadata.get("catalogueBytes"), int) and 0 <= metadata["catalogueBytes"] <= 3 * 1024 * 1024 and
             isinstance(metadata.get("indexBytes"), int) and isinstance(metadata.get("defaultBytes"), int) and
             0 <= metadata["indexBytes"] + metadata["defaultBytes"] <= 400 * 1024,
             9, "per-file, catalogue or default cold-load budget exceeded")
    return silk
