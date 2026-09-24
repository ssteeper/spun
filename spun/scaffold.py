"""Bark, knots and eucalypt leaves are fixed ENV graph threads."""

from dataclasses import dataclass
import math

from .builder import PlanGraph
from .geometry import catmull_rom, point_on
from .kinds import BY_NAME, COLORS


def _rgb(hexcode):
    return tuple(bytes.fromhex(hexcode[1:]))


# A frame corner closer than this to the bark is tied straight onto it.
BARK_SNAP = 12.0
# Longest side twig carrying a frame anchor.
TWIG_MAX = 90.0


@dataclass(frozen=True)
class BranchSpec:
    """A long branch, the frame corners it carries and its eucalypt leaves.

    ``anchors`` holds ``(polygon index, (x, y))`` desired corners: a corner
    within ``BARK_SNAP`` of the bark sits on it; otherwise a short, nearly
    straight side twig (≤ ``TWIG_MAX``) grows from the nearest bark point.
    """

    controls: tuple[tuple[float, float], ...]
    anchors: tuple[tuple[int, tuple[float, float]], ...]
    leaves: tuple[tuple[float, float, float], ...] = ()


def _resolve(trunk_points, target):
    """Return (trunk sample index, corner point, twig length) for a desired corner."""
    index = min(range(len(trunk_points)), key=lambda i: math.dist(trunk_points[i], target))
    distance = math.dist(trunk_points[index], target)
    if distance <= BARK_SNAP:
        return index, trunk_points[index], 0.0
    if distance > TWIG_MAX:
        raise ValueError(f"frame corner {target} is {distance:.0f} px from its branch")
    return index, tuple(map(float, target)), distance


def frame_polygon(branches, shared=None):
    """Frame corners exactly as ``orb_scaffold`` will place them, in index order.

    ``shared`` maps colony corner indices to points on an earlier orb's frame.
    """
    corners = dict(shared or {})
    for branch in branches:
        trunk = catmull_rom(branch.controls, interval=8)
        for index, target in branch.anchors:
            if index in corners:
                raise ValueError("duplicate frame anchor")
            corners[index] = _resolve(trunk, target)[1]
    if sorted(corners) != list(range(len(corners))):
        raise ValueError("frame corner indices must be contiguous from zero")
    return tuple(corners[i] for i in range(len(corners)))


def _twig_styles(count, rng, start_width=None, end_width=None):
    bark0, bark1 = _rgb("#5b3f2a"), _rgb("#8a6a48")
    definition = BY_NAME["SCAFFOLD"]
    styles = []
    for i in range(count):
        t = i / max(count - 1, 1)
        noise = 1 + rng.uniform(-0.06, 0.06)
        color = tuple(max(0, min(255, round(((1-t)*a + t*b) * noise)))
                      for a, b in zip(bark0, bark1))
        start = definition.width if start_width is None else start_width
        end = definition.width_end if end_width is None else end_width
        width = start + (end - start)*t
        styles.append((width, color, definition.alpha))
    return styles


def _fixed_spline(graph, controls):
    points = catmull_rom(controls, interval=8)
    return [graph.node(point, fixed=True) for point in points]


def _leaf(graph, root, length, direction):
    """Two gently arched lanceolate margins, a curved midrib, and paired veins."""
    base = graph.position(root)
    forward = (math.cos(direction), math.sin(direction))
    normal = (-forward[1], forward[0])

    def place(along, across):
        return (base[0]+forward[0]*length*along+normal[0]*across,
                base[1]+forward[1]*length*along+normal[1]*across)

    tip = place(1, 0)
    broad = 0.16*length
    upper = _fixed_spline(graph, [base, place(0.19, broad*0.48),
                                  place(0.58, broad), tip])
    lower = _fixed_spline(graph, [base, place(0.19, -broad*0.48),
                                  place(0.58, -broad), tip])
    margin = upper + list(reversed(lower[1:-1])) + [root]
    vein = _fixed_spline(graph, [base, place(0.26, 2), place(0.69, 3), tip])
    shades = ((margin, COLORS["leaf"]), (vein, COLORS["leaf_vein"]))
    for path, color in shades:
        graph.add_thread(path, "LEAF", env=True,
                         styles=[(BY_NAME["LEAF"].width, _rgb(color), 0.9)]*(len(path)-1))
    for part in (0.30, 0.53, 0.72):
        for side in (-1, 1):
            a = graph.node(place(part, 2), fixed=True)
            b = graph.node(place(min(part+0.15, 0.91), side*broad*(1-part)), fixed=True)
            if a != b:
                graph.add_thread([a, b], "LEAF", env=True,
                                 styles=[(BY_NAME["LEAF"].width, _rgb(COLORS["leaf_vein"]), 0.7)])


def _side_twig(graph, rng, source, tip, root_width, bend_sign, fork):
    """A short, nearly straight tapering twig with one gentle bend and an optional spur."""
    dx, dy = tip[0]-source[0], tip[1]-source[1]
    span = math.hypot(dx, dy)
    nx, ny = -dy/span, dx/span
    bend = bend_sign*0.06*span
    controls = (source,
                (source[0]+0.35*dx+nx*bend, source[1]+0.35*dy+ny*bend),
                (source[0]+0.70*dx+nx*bend*0.7, source[1]+0.70*dy+ny*bend*0.7), tip)
    twig = _fixed_spline(graph, controls)
    start = min(3.6, max(2.2, 0.55*root_width))
    graph.add_thread(twig, "SCAFFOLD", env=True,
                     styles=_twig_styles(len(twig)-1, rng, start_width=start, end_width=1.3))
    if fork and len(twig) > 4:
        base = graph.position(twig[len(twig)//2])
        angle = math.atan2(dy, dx) - bend_sign*0.62
        spur_length = 0.38*span
        spur_tip = (base[0]+spur_length*math.cos(angle), base[1]+spur_length*math.sin(angle))
        spur = _fixed_spline(graph, (base, point_on(base, spur_tip, 0.35),
                                     point_on(base, spur_tip, 0.7), spur_tip))
        graph.add_thread([twig[len(twig)//2]]+spur[1:], "SCAFFOLD", env=True,
                         styles=_twig_styles(len(spur)-1, rng, start_width=0.8*start,
                                             end_width=1.0))
    return twig[-1]


def orb_scaffold(graph: PlanGraph, polygon, rng, branches, shared=()):
    """Compose 2–5 long branches; frame corners sit on bark or on short side twigs.

    ``shared`` corners are left as None for the colony to attach to earlier silk.
    """
    if not 2 <= len(branches) <= 5:
        raise ValueError("an orb requires two to five scaffold branches")
    if tuple(polygon) != frame_polygon(branches, {i: polygon[i] for i in shared}):
        raise ValueError("frame polygon must come from frame_polygon(branches)")
    anchors = [None]*len(polygon)
    arrival = None
    for branch in branches:
        if not 4 <= len(branch.controls) <= 7 or not branch.anchors:
            raise ValueError("each branch needs 4–7 controls and at least one anchor")
        points = catmull_rom(branch.controls, interval=8)
        trunk = _fixed_spline(graph, branch.controls)
        trunk_styles = _twig_styles(len(trunk)-1, rng)
        graph.add_thread(trunk, "SCAFFOLD", env=True, styles=trunk_styles)
        for index, target in branch.anchors:
            if anchors[index] is not None:
                raise ValueError("duplicate frame anchor")
            at, corner, twig_length = _resolve(points, target)
            if twig_length == 0:
                anchors[index] = trunk[at]
            else:
                anchors[index] = _side_twig(
                    graph, rng, points[at], corner,
                    trunk_styles[min(at, len(trunk_styles)-1)][0],
                    1 if index % 2 else -1, fork=twig_length > 45 and index % 3 == 0)
            if index == 0:
                arrival = trunk[0]
        for number, fraction in enumerate((0.27, 0.66)):
            start_at = trunk[round(fraction*(len(trunk)-1))]
            point = graph.position(start_at)
            previous = graph.position(trunk[max(0, round(fraction*(len(trunk)-1))-2)])
            tangent = math.atan2(point[1]-previous[1], point[0]-previous[0])
            side = 1 if number == 0 else -1
            tip = (point[0]+28*math.cos(tangent+side*0.8),
                   point[1]+28*math.sin(tangent+side*0.8))
            twiglet = _fixed_spline(graph, (point,
                                             (point[0]+7*math.cos(tangent), point[1]+7*math.sin(tangent)),
                                             (point[0]+19*math.cos(tangent+side*0.5),
                                              point[1]+19*math.sin(tangent+side*0.5)), tip))
            graph.add_thread(twiglet, "SCAFFOLD", env=True,
                             styles=_twig_styles(len(twiglet)-1, rng, start_width=3.2))
        for fraction, size, angle in branch.leaves:
            _leaf(graph, trunk[round(fraction*(len(trunk)-1))], size, angle)
    if any((anchor is None) != (i in shared) for i, anchor in enumerate(anchors)) \
            or arrival is None:
        raise ValueError("every frame anchor needs a scaffold connection")
    return anchors, arrival
