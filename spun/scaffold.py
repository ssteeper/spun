"""Bark, knots and eucalypt leaves are fixed ENV graph threads."""

from dataclasses import dataclass
import math

from .builder import PlanGraph
from .geometry import catmull_rom
from .kinds import BY_NAME, COLORS


def _rgb(hexcode):
    return tuple(bytes.fromhex(hexcode[1:]))


@dataclass(frozen=True)
class BranchSpec:
    """A long outer branch, its attachment forks and placed eucalypt leaves."""

    controls: tuple[tuple[float, float], ...]
    anchors: tuple[tuple[int, float], ...]
    leaves: tuple[tuple[float, float, float], ...] = ()


def _twig_styles(count, rng, start_width=None):
    bark0, bark1 = _rgb("#5b3f2a"), _rgb("#8a6a48")
    definition = BY_NAME["SCAFFOLD"]
    styles = []
    for i in range(count):
        t = i / max(count - 1, 1)
        noise = 1 + rng.uniform(-0.06, 0.06)
        color = tuple(max(0, min(255, round(((1-t)*a + t*b) * noise)))
                      for a, b in zip(bark0, bark1))
        width = (definition.width if start_width is None else start_width) + (
            definition.width_end - (definition.width if start_width is None else start_width))*t
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


def orb_scaffold(graph: PlanGraph, polygon, rng, branches):
    """Compose 2–4 long branches, each supporting multiple named frame anchors."""
    if not 2 <= len(branches) <= 4:
        raise ValueError("an orb requires two to four scaffold branches")
    anchors = [None]*len(polygon)
    arrival = None
    for branch in branches:
        if not 4 <= len(branch.controls) <= 7 or len(branch.anchors) < 2:
            raise ValueError("each branch needs 4–7 controls and at least two anchors")
        trunk = _fixed_spline(graph, branch.controls)
        trunk_styles = _twig_styles(len(trunk)-1, rng)
        graph.add_thread(trunk, "SCAFFOLD", env=True, styles=trunk_styles)
        for index, fraction in branch.anchors:
            if anchors[index] is not None or not 0 <= fraction <= 1:
                raise ValueError("duplicate anchor or invalid branch position")
            start_at = trunk[round(fraction*(len(trunk)-1))]
            tip = polygon[index]
            source = graph.position(start_at)
            dx, dy = tip[0]-source[0], tip[1]-source[1]
            normal = (-dy, dx)
            norm = max(math.hypot(*normal), 1)
            bend = 0.055*math.hypot(dx, dy)
            controls = (source,
                        (source[0]+0.34*dx+normal[0]*bend/norm,
                         source[1]+0.34*dy+normal[1]*bend/norm),
                        (source[0]+0.71*dx-normal[0]*bend/norm,
                         source[1]+0.71*dy-normal[1]*bend/norm), tip)
            fork = _fixed_spline(graph, controls)
            width_at_root = trunk_styles[
                min(len(trunk_styles)-1, round(fraction*(len(trunk)-1)))][0]
            graph.add_thread(fork, "SCAFFOLD", env=True,
                             styles=_twig_styles(len(fork)-1, rng, start_width=width_at_root))
            anchors[index] = fork[-1]
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
    if any(anchor is None for anchor in anchors) or arrival is None:
        raise ValueError("every frame anchor needs a scaffold connection")
    return anchors, arrival
