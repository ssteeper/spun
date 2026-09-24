"""Snare programs: the net-casting spider's held net, the bolas, and the gumfoot cobweb.

Each program runs a single Builder on the plan graph exactly like the orb (§4.1):
scaffold first, then spin/walk_to/remove/rest. Snares are not relaxed; their
lines are laid at their final, held or hanging positions.
"""

from dataclasses import dataclass
import math
import zlib

import numpy as np

from .builder import Builder, PlanGraph
from .emit import emit
from .kinds import BY_NAME, COLORS
from .pacing import pace
from .scaffold import leaf, polyline, twig
from .silkfile import write_silk
from .spider import rest_points_px
from .validate import validate


def _rgb(hexcode):
    return tuple(bytes.fromhex(hexcode[1:]))


@dataclass
class SnareResult:
    data: bytes
    records: np.ndarray
    beads: np.ndarray
    metadata: dict
    rest: dict
    graph: PlanGraph
    relaxation: None
    env_fraction: float
    width: int
    height: int
    builder_count: int


def _rngs(species_id):
    seed = zlib.crc32(species_id.encode("utf-8"))
    # Bark and litter draw from their own stream, as for the orbs.
    return np.random.default_rng(seed), np.random.default_rng(seed ^ 0x9E3779B9)


def _finish(species_id, width, height, mm_per_px, duration, graph):
    records, beads, rest = emit(graph)
    data = write_silk(width, height, 1, records, beads)
    timing = pace(records, duration)
    metadata = {
        "kind": "snare", "anchor": [rest[0]["x"], rest[0]["y"]], "mmPerUnit": mm_per_px,
        "timeline": timing["timeline"], "stages": timing["stages"],
        "rests": {i: (pose["x"], pose["y"]) for i, pose in rest.items()},
        "catalogueBytes": len(data), "indexBytes": 0, "defaultBytes": 0,
    }
    validate(data, metadata)
    return SnareResult(data, records, beads, metadata, rest, graph, None,
                       timing["envFraction"], width, height, 1)


def _style(graph, thread, color, alpha=None, width=None):
    kind = BY_NAME[graph.threads[thread].kind]
    graph.threads[thread].styles = [(kind.width if width is None else width, _rgb(color),
                                     kind.alpha if alpha is None else alpha)] * \
        (len(graph.threads[thread].path)-1)


def _nearest(graph, nodes, point):
    return min(nodes, key=lambda node: math.dist(graph.position(node), point))


def _crossings(graph, nodes, y):
    """x of every crossing of the level line ``y`` with a scaffold polyline."""
    found = []
    for a, b in zip(nodes, nodes[1:]):
        (x0, y0), (x1, y1) = graph.position(a), graph.position(b)
        if (y0 - y)*(y1 - y) < 0:
            found.append(x0 + (y - y0)/(y1 - y0)*(x1 - x0))
    return sorted(found)


def _thread_of(graph, nodes):
    return next(i for i, thread in enumerate(graph.threads) if thread.path == nodes)


def _at_x(graph, nodes, x):
    """The point of a left-to-right scaffold polyline at abscissa ``x``."""
    for a, b in zip(nodes, nodes[1:]):
        (x0, y0), (x1, y1) = graph.position(a), graph.position(b)
        if min(x0, x1) <= x <= max(x0, x1) and x0 != x1:
            return (x, y0 + (x - x0)/(x1 - x0)*(y1 - y0))
    raise ValueError(f"x={x} is beyond the scaffold line")


# --- Deinopis: a held, combed cribellate net ----------------------------------------


@dataclass(frozen=True)
class NetParameters:
    id: str
    width: int
    height: int
    mm_per_px: float
    duration: float
    twig: tuple[tuple[float, float], ...]
    leaves: tuple[tuple[float, float, float], ...]
    rest: tuple[float, float]           # spinnerets, on the 0.25 px grid
    stays: tuple[float, float]          # x of the two side stays on the twig
    row_spacing: float = 4.5
    zig: float = 4.5
    amplitude: float = 1.2
    strand: float = 0.6


def _offset(points, distance):
    """Miter-offset a polyline so each offset segment is parallel at ``distance``."""
    normals = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        span = math.hypot(x1-x0, y1-y0)
        normals.append((-(y1-y0)/span, (x1-x0)/span))
    result = []
    for j in range(1, len(points)-1):
        (ax, ay), (bx, by) = normals[j-1], normals[j]
        mx, my = ax+bx, ay+by
        scale = distance/(mx*ax+my*ay)
        result.append((points[j][0]+mx*scale, points[j][1]+my*scale))
    return result


def net_casting(spec: NetParameters) -> SnareResult:
    graph = PlanGraph()
    _, bark = _rngs(spec.id)
    branch = twig(graph, bark, spec.twig)
    for fraction, size, angle in spec.leaves:
        leaf(graph, branch[round(fraction*(len(branch)-1))], size, angle)
    x, y = spec.rest
    heading = math.pi/2
    tips = rest_points_px(spec.id, x, y, heading, spec.mm_per_px)
    # Tarsi I–II (legs 0, 1, 4, 5) hold the corners; head-down, legs 1/5 are the upper pair.
    top_right, top_left = graph.node(tips[1]), graph.node(tips[5])
    bottom_right, bottom_left = graph.node(tips[0]), graph.node(tips[4])
    spinnerets = graph.node(spec.rest)
    stem = _nearest(graph, branch, (x, 0))
    stay_left = _nearest(graph, branch, (spec.stays[0], y))
    stay_right = _nearest(graph, branch, (spec.stays[1], y))

    spider = Builder(graph, branch[0])
    spider.walk_to(stem)
    spider.spin([stem, spinnerets], "BRIDGE")
    for stay in (stay_left, stay_right):
        spider.walk_to(stay)
        spider.spin([stay, spinnerets], "FRAME")
    # The Y: two arms from her hanging point to the net's upper corners.
    spider.spin([spinnerets, top_left], "FRAME")
    spider.spin([top_left, top_right], "FRAME")
    spider.spin([top_right, spinnerets], "FRAME")
    spider.walk_to(top_left)
    frame = spider.spin([top_left, bottom_left, bottom_right, top_right], "FRAME")

    (xl, yt), (xr, yb) = graph.position(top_left), graph.position(bottom_right)
    rows = int((yb-yt)/spec.row_spacing - 0.5)
    spacing = (yb-yt)/(rows+1)
    zigs = max(2, round((xr-xl)/spec.zig))
    for i in range(1, rows+1):
        row_y = yt + i*spacing
        left = graph.attach(frame, (xl, row_y))
        right = graph.attach(frame, (xr, row_y))
        centre = [(xl + j*(xr-xl)/zigs, row_y + (spec.amplitude*(-1)**(i+j) if 0 < j < zigs else 0))
                  for j in range(zigs+1)]
        data = {"level": (rows-i)/rows, "band": 1/rows}
        spider.walk_to(left)
        # She combs each zig twice: out on one side of the axis, back on the other.
        forward = spider.spin([left, *_offset(centre, spec.strand), right], "CRIBELLATE", data=data)
        back = spider.spin([right, *reversed(_offset(centre, -spec.strand)), left], "CRIBELLATE",
                           data=data)
        for thread in (forward, back):
            _style(graph, thread, COLORS["cribellate"])
    spider.walk_to(spinnerets)
    spider.rest("net", heading)
    return _finish(spec.id, spec.width, spec.height, spec.mm_per_px, spec.duration, graph)


# --- Ordgarius: trapeze, bolas and spindle egg sacs ---------------------------------


@dataclass(frozen=True)
class BolasParameters:
    id: str
    width: int
    height: int
    mm_per_px: float
    duration: float
    branch: tuple[tuple[float, float], ...]
    leaves: tuple[tuple[float, float, float], ...]
    trapeze_mm: float
    hang_x: float                        # fraction along the trapeze where she hangs
    hang_px: float                       # drop from trapeze to spinnerets
    bolas_px: float                      # spinnerets to the end of the glue
    sticky_px: float                     # the last, STICKY sub-record
    sacs: tuple[tuple[float, float, float, float], ...]   # (x, stalk px, length px, tilt)


def _spindle(spider, graph, top, length, half_width, tilt, rng):
    """A pointed brown spindle: two outline meridians plus a woolly double wrap."""
    tx, ty = graph.position(top)
    ax, ay = math.sin(tilt), math.cos(tilt)
    nx, ny = ay, -ax
    count = 16

    def side(sign):
        return [(tx + ax*length*t + nx*sign*half_width*math.sin(math.pi*t)**0.8,
                 ty + ay*length*t + ny*sign*half_width*math.sin(math.pi*t)**0.8)
                for t in (k/count for k in range(1, count))]
    right, left = side(1), side(-1)
    bottom = graph.node((tx + ax*length, ty + ay*length))
    color = COLORS["eggsac_ordgarius"]
    outline = spider.spin([top, *right, bottom], "EGGSAC")
    _style(graph, outline, color, 1.0, 2.0)
    back = spider.spin([bottom, *reversed(left), top], "EGGSAC")
    _style(graph, back, color, 1.0, 2.0)
    right_nodes = graph.threads[outline].path[1:-1]
    left_nodes = graph.threads[back].path[-2:0:-1]
    # Down and up again, crossing the sac: a ridged, woolly wrap.
    for first, order in ((0, range(count-1)), (1, reversed(range(count-1)))):
        path = [(right_nodes if (k+first) % 2 else left_nodes)[k] for k in order]
        end = bottom if first == 0 else top
        start = top if first == 0 else bottom
        wrap = spider.spin([start, *path, end], "EGGSAC")
        _style(graph, wrap, "#94693f", 0.95, 1.1 + 0.3*rng.random())


def bolas(spec: BolasParameters) -> SnareResult:
    graph = PlanGraph()
    rng, bark = _rngs(spec.id)
    branch = twig(graph, bark, spec.branch)
    branch_thread = len(graph.threads)-1
    for fraction, size, angle in spec.leaves:
        leaf(graph, branch[round(fraction*(len(branch)-1))], size, angle)
    spider = Builder(graph, branch[0])

    for x, stalk, length, tilt in spec.sacs:
        tie = graph.attach(branch_thread, _at_x(graph, branch, x))
        spider.walk_to(tie)
        tx, ty = graph.position(tie)
        top = graph.node((tx + stalk*math.sin(tilt), ty + stalk*math.cos(tilt)))
        hold = spider.spin([tie, top], "EGGSAC")
        _style(graph, hold, COLORS["dry"], 0.8, 0.8)
        _spindle(spider, graph, top, length, 0.19*length, tilt, rng)
        spider.walk_to(tie)

    # The trapeze: a level line between the two points where the arching branch
    # is exactly trapeze_mm apart.
    span = spec.trapeze_mm/spec.mm_per_px
    low, high = min(graph.position(n)[1] for n in branch), max(graph.position(n)[1] for n in branch)
    level = None
    for _ in range(60):
        middle = (low+high)/2
        crossing = _crossings(graph, branch, middle)
        if len(crossing) >= 2 and crossing[-1]-crossing[0] > span:
            high = middle
        else:
            low = middle
        level = middle
    crossing = _crossings(graph, branch, level)
    left = graph.attach(branch_thread, (crossing[0], level))
    right = graph.attach(branch_thread, (crossing[-1], level))
    spider.walk_to(left)
    trapeze = spider.spin([left, right], "BRIDGE")
    (x0, y0), (x1, y1) = graph.position(left), graph.position(right)
    hang = graph.attach(trapeze, (x0+spec.hang_x*(x1-x0), y0+spec.hang_x*(y1-y0)))
    spider.walk_to(hang)
    hx, hy = graph.position(hang)
    spinnerets = graph.node((round(hx*4)/4, round((hy+spec.hang_px)*4)/4))
    spider.spin([hang, spinnerets], "FRAME")
    heading = 0.0
    sx, sy = graph.position(spinnerets)
    # Left leg II's rest tarsus lies on the line (C4): the line runs through it.
    tarsus = rest_points_px(spec.id, sx, sy, heading, spec.mm_per_px)[1]
    ux, uy = tarsus[0]-sx, tarsus[1]-sy
    reach = math.hypot(ux, uy)
    ux, uy = ux/reach, uy/reach
    glue_start = (sx+ux*(spec.bolas_px-spec.sticky_px), sy+uy*(spec.bolas_px-spec.sticky_px))
    line = spider.spin([spinnerets, tarsus, glue_start], "BOLAS")
    _style(graph, line, COLORS["bolas"])
    globule = spider.spin([graph.threads[line].path[-1],
                           (sx+ux*spec.bolas_px, sy+uy*spec.bolas_px)], "BOLAS", sticky=True)
    _style(graph, globule, COLORS["bolas"])
    spider.walk_to(spinnerets)
    spider.rest("hanging", heading)
    return _finish(spec.id, spec.width, spec.height, spec.mm_per_px, spec.duration, graph)


# --- Latrodectus: retreat, tangle and gumfoot lines under a rail --------------------


@dataclass(frozen=True)
class CobwebParameters:
    id: str
    width: int
    height: int
    mm_per_px: float
    duration: float
    rail: tuple[float, float, float]     # post x (inner face), rail top y, rail bottom y
    post_width: float
    ground: tuple[tuple[float, float], ...]
    litter: tuple[tuple[float, float, float], ...]   # (x, size px, angle)
    retreat: tuple[float, float, float, float]      # centre x, y, half-width, half-height
    tangle_box: tuple[float, float, float, float]   # x0, y0, x1, y1 (projected)
    depth: float                                    # half-depth of the 3D box, px
    points: tuple[int, int]
    retreat_segments: tuple[int, int]
    gumfoot: tuple[int, int]


_TIMBER = "#a09684"
_TIMBER_DARK = "#6a6358"
_GRAIN = "#7c7467"


def _timber(graph, bark, spec):
    """A weathered rail meeting a post: board edges, 3–5 grain lines, a ground line."""
    post, top, bottom = spec.rail
    inner, outer = post, post - spec.post_width
    ground_y = max(y for _, y in spec.ground)
    right = spec.width
    underside = polyline(graph, [(inner, bottom)] + [(x, bottom + 0.6*math.sin(x/97))
                                                     for x in range(int(inner)+40, right, 40)]
                         + [(right, bottom)], "SCAFFOLD", _TIMBER, 4.2)
    polyline(graph, [(outer, top)] + [(x, top + 0.5*math.sin(x/131)) for x in
                                      range(int(outer)+60, right, 60)] + [(right, top)],
             "SCAFFOLD", _TIMBER, 4.0)
    face = polyline(graph, [(inner, bottom)] + [(inner + 0.7*math.sin(y/83), y) for y in
                                                range(int(bottom)+40, int(ground_y)-10, 40)]
                    + [(inner, ground_y-6)], "SCAFFOLD", _TIMBER, 4.2)
    polyline(graph, [(outer, top)] + [(outer, y) for y in range(int(top)+50, int(ground_y), 50)]
             + [(outer, ground_y-4)], "SCAFFOLD", _TIMBER_DARK, 2.6)
    # Grain: long wavering lines along the rail, some ending in a split.
    lines = int(bark.integers(3, 6))
    for k in range(lines):
        y0 = top + (k+1)*(bottom-top)/(lines+1) + bark.uniform(-4, 4)
        start = inner + bark.uniform(10, 120)
        end = right - bark.uniform(0, 260) if k % 2 else right
        phase, wave = bark.uniform(0, math.tau), bark.uniform(1.2, 3.2)
        grain = [(x, y0 + wave*math.sin(x/bark.uniform(70, 150) + phase))
                 for x in np.arange(start, end, 36.0)] + [(end, y0)]
        polyline(graph, grain, "SCAFFOLD", _GRAIN, 1.4 + 0.6*bark.random(), 0.9)
    for k in range(2):
        x0 = outer + (k+1)*spec.post_width/3 + bark.uniform(-3, 3)
        polyline(graph, [(x0 + 1.5*math.sin(y/61 + k), y) for y in
                         np.arange(bottom+20, ground_y-30, 34.0)], "SCAFFOLD", _GRAIN, 1.1, 0.85)
    ground = polyline(graph, spec.ground, "SCAFFOLD", "#4a3a2b", 3.0)
    for x, size, angle in spec.litter:
        base = _at_x(graph, ground, x)
        root = graph.node((base[0], base[1]-1.5), fixed=True)
        _litter_leaf(graph, root, size, angle, bark)
    return underside, face, ground


def _litter_leaf(graph, root, size, angle, rng):
    """A dry, curled eucalypt fragment lying on the ground."""
    bx, by = graph.position(root)
    fx, fy = math.cos(angle), math.sin(angle)
    nx, ny = -fy, fx
    curl = rng.uniform(-0.25, 0.25)

    def at(t, w):
        bend = curl*size*t*t
        return (bx + fx*size*t + nx*(w+bend), by + fy*size*t + ny*(w+bend))
    broad = 0.17*size*rng.uniform(0.8, 1.1)
    outline = ([root] + [at(t, broad*math.sin(math.pi*t)**0.7) for t in np.linspace(0.1, 0.9, 5)]
               + [at(1, 0)] + [at(t, -broad*math.sin(math.pi*t)**0.7)
                               for t in np.linspace(0.9, 0.1, 5)] + [root])
    shade = ("#6e5234", "#7d6040", "#5c4430")[int(rng.integers(0, 3))]
    polyline(graph, outline[:-1], "SCAFFOLD", shade, 1.1, 0.9)
    polyline(graph, [at(0.05, 0), at(0.5, 0), at(0.95, 0)], "SCAFFOLD", COLORS["leaf_vein"], 0.8, 0.8)


def cobweb(spec: CobwebParameters) -> SnareResult:
    graph = PlanGraph()
    rng, bark = _rngs(spec.id)
    underside, face, ground = _timber(graph, bark, spec)
    rail_thread = _thread_of(graph, underside)
    post_thread = _thread_of(graph, face)
    ground_thread = _thread_of(graph, ground)
    post, _, bottom = spec.rail
    cx, cy, half_w, half_h = spec.retreat
    retreat_color = COLORS["retreat"]

    # Retreat: a dense wandering silk lining lashed into the rail/post corner.
    spider = Builder(graph, _nearest(graph, underside, (cx, bottom)))
    target = int(rng.integers(*spec.retreat_segments))
    laid = 0
    retreat_nodes = []
    point = graph.position(spider.current)
    while laid < target:
        path = [spider.current]
        for _ in range(int(rng.integers(6, 11))):
            for _ in range(40):
                step = rng.uniform(6, 15)
                angle = rng.uniform(0, math.tau)
                candidate = (point[0] + step*math.cos(angle), point[1] + step*math.sin(angle))
                inside = (((candidate[0]-cx)/half_w)**2 + ((candidate[1]-cy)/half_h)**2 < 1 or
                          math.dist(candidate, (cx, cy)) < math.dist(point, (cx, cy)) - 3)
                if inside and candidate[0] > post+2 and candidate[1] > bottom+2:
                    node = graph.node(candidate)
                    if node not in path and node not in retreat_nodes:
                        break
            else:
                raise ValueError("retreat walk cannot find a fresh point")
            path.append(node)
            point = candidate
        # Each run is lashed back to the timber: alternately the rail and the post.
        if len(retreat_nodes) // 8 % 2:
            tie = graph.attach(post_thread, _on_face(graph, face, point[1]))
        else:
            tie = graph.attach(rail_thread, _at_x(graph, underside, point[0]))
        if tie not in path:
            path.append(tie)
        thread = spider.spin(path, "RETREAT")
        _style(graph, thread, retreat_color)
        retreat_nodes.extend(node for node in path[1:] if node != tie)
        laid += len(path)-1
        point = graph.position(path[-1])

    # Tangle: 3-D points; every thread leaves an existing node she has walked to.
    x0, y0, x1, y1 = spec.tangle_box
    count = int(rng.integers(*spec.points))
    depth = {node: 0.5 for node in retreat_nodes}
    tangle = []
    alpha0, alpha1 = BY_NAME["TANGLE"].alpha, BY_NAME["TANGLE"].alpha_max

    def spin_tangle(start, end):
        spider.walk_to(start)
        thread = spider.spin([start, end], "TANGLE")
        near = (depth.get(start, 0.5) + depth.get(end, 0.5))/2
        _style(graph, thread, COLORS["dry"], alpha0 + (alpha1-alpha0)*near)

    sources = list(retreat_nodes)
    while len(tangle) < count:
        roll = rng.random()
        if roll < 0.33 or not tangle:
            # A fresh drop line from the rail's underside, reached along the timber.
            start = graph.attach(rail_thread, _at_x(graph, underside, rng.uniform(x0+40, x1-60)))
        elif roll < 0.35:
            start = retreat_nodes[int(rng.integers(len(retreat_nodes)))]
        else:
            start = tangle[int(rng.integers(len(tangle)))]
        sx, sy = graph.position(start)
        z = min(1.0, max(0.0, depth.get(start, 0.5) + rng.normal(0, 0.25)))
        for _ in range(60):
            length = rng.uniform(30, 160)
            # Biased vertical: mostly down, sometimes back up towards the rail.
            angle = math.pi/2 + rng.normal(0, 0.45) + (math.pi if rng.random() < 0.18 else 0)
            end = (sx + length*math.cos(angle) + 0.3*spec.depth*(z-depth.get(start, 0.5)),
                   sy + length*math.sin(angle))
            if x0 <= end[0] <= x1 and y0 <= end[1] <= y1:
                break
        else:
            continue
        node = graph.node(end)
        if node in depth:
            continue
        depth[node] = z
        spin_tangle(start, node)
        tangle.append(node)
        sources.append(node)
        # Cross-links: a thread onward to a nearby existing point.
        if rng.random() < 0.55:
            partners = [other for other in sources if other != node and other not in
                        retreat_nodes and 30 <= math.dist(graph.position(other), end) <= 160]
            if partners:
                other = min(partners, key=lambda o: abs(graph.position(o)[0]-end[0]) +
                            0.3*abs(graph.position(o)[1]-end[1]) + 40*rng.random())
                spin_tangle(node, other)
        # Upward stays to the rail's underside.
        if rng.random() < 0.12 and end[1]-bottom < 140 and end[0] < spec.width-4:
            stay = graph.attach(rail_thread, _at_x(graph, underside, end[0] + rng.uniform(-20, 20)))
            spin_tangle(node, stay)

    # Gumfoot lines: from the lowest tangle points straight down to the ground.
    lines = int(rng.integers(*spec.gumfoot))
    # One foot per x-band across the tangle, from each band's lowest point.
    xs = [graph.position(n)[0] for n in tangle]
    left_x, right_x = min(xs), max(xs)
    chosen = []
    for band in range(lines):
        lo = left_x + band*(right_x-left_x)/lines
        hi = left_x + (band+1)*(right_x-left_x)/lines + 1e-6
        members = [n for n in tangle if lo <= graph.position(n)[0] < hi and
                   all(abs(graph.position(n)[0]-graph.position(o)[0]) > 14 for o in chosen)]
        if members:
            chosen.append(max(members, key=lambda n: graph.position(n)[1]))
    for node in sorted(tangle, key=lambda n: -graph.position(n)[1]):
        if len(chosen) == lines:
            break
        if all(abs(graph.position(node)[0]-graph.position(o)[0]) > 14 for o in chosen):
            chosen.append(node)
    if len(chosen) != lines:
        raise ValueError(f"only {len(chosen)} of {lines} gumfoot lines find spread-out tangle points")
    for node in sorted(chosen, key=lambda n: graph.position(n)[0]):
        tx, ty = graph.position(node)
        foot = graph.attach(ground_thread, _at_x(graph, ground, tx + rng.uniform(-12, 12)))
        fx, fy = graph.position(foot)
        split = (tx + 0.88*(fx-tx), ty + 0.88*(fy-ty))
        spider.walk_to(node)
        upper = spider.spin([node, split], "GUMFOOT")
        lower = spider.spin([graph.threads[upper].path[-1], foot], "GUMFOOT", sticky=True)
        _style(graph, upper, COLORS["dry"])
        _style(graph, lower, COLORS["sticky"])
    mouth = max(retreat_nodes, key=lambda n: graph.position(n)[1] + 0.3*graph.position(n)[0])
    spider.walk_to(mouth)
    mx, my = graph.position(mouth)
    heading = math.atan2((y0+y1)/2 - my, (x0+x1)/2 - mx)
    spider.rest("retreat", heading)
    return _finish(spec.id, spec.width, spec.height, spec.mm_per_px, spec.duration, graph)


def _on_face(graph, nodes, y):
    """The point of a top-to-bottom scaffold polyline at ordinate ``y``."""
    for a, b in zip(nodes, nodes[1:]):
        (x0, y0), (x1, y1) = graph.position(a), graph.position(b)
        if min(y0, y1) <= y <= max(y0, y1) and y0 != y1:
            return (x0 + (y - y0)/(y1 - y0)*(x1 - x0), y)
    raise ValueError(f"y={y} is beyond the scaffold line")
