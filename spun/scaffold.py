"""Bark, knots and eucalypt leaves are fixed ENV graph threads."""

import math

from .builder import PlanGraph
from .geometry import catmull_rom
from .kinds import BY_NAME, COLORS


def _rgb(hexcode):
    return tuple(bytes.fromhex(hexcode[1:]))


def _twig_styles(count, rng):
    bark0, bark1 = _rgb("#5b3f2a"), _rgb("#8a6a48")
    definition = BY_NAME["SCAFFOLD"]
    styles = []
    for i in range(count):
        t = i / max(count - 1, 1)
        noise = 1 + rng.uniform(-0.06, 0.06)
        color = tuple(max(0, min(255, round(((1-t)*a + t*b) * noise)))
                      for a, b in zip(bark0, bark1))
        width = definition.width + t * (definition.width_end - definition.width)
        styles.append((width, color, definition.alpha))
    return styles


def orb_scaffold(graph: PlanGraph, polygon, rng):
    """Eight separate outer twigs, one attached to each frame anchor."""
    center = (sum(x for x, _ in polygon)/len(polygon),
              sum(y for _, y in polygon)/len(polygon))
    anchors = []
    start = None
    for index, anchor in enumerate(polygon):
        angle = math.atan2(anchor[1]-center[1], anchor[0]-center[0])
        ux, uy = math.cos(angle), math.sin(angle)
        normal = (-uy, ux)
        controls = [
            (anchor[0]+ux*150 + normal[0]*14, anchor[1]+uy*150 + normal[1]*14),
            (anchor[0]+ux*118 - normal[0]*10, anchor[1]+uy*118 - normal[1]*10),
            (anchor[0]+ux*72 + normal[0]*12, anchor[1]+uy*72 + normal[1]*12),
            anchor,
        ]
        sampled = catmull_rom(controls, interval=8)
        nodes = [graph.node(point, fixed=True) for point in sampled]
        graph.add_thread(nodes, "SCAFFOLD", env=True,
                         styles=_twig_styles(len(nodes)-1, rng))
        anchors.append(nodes[-1])
        if index == 0:
            start = nodes[0]
        # A knot and a shorter branchlet give the bark nonuniform silhouettes.
        branch = nodes[max(2, len(nodes)//2)]
        bx, by = graph.position(branch)
        tip = (bx + normal[0]*24 + ux*12, by + normal[1]*24 + uy*12)
        branch_nodes = [branch, graph.node(((bx+tip[0])*0.5, (by+tip[1])*0.5), fixed=True),
                        graph.node(tip, fixed=True)]
        graph.add_thread(branch_nodes, "SCAFFOLD", env=True,
                         styles=_twig_styles(2, rng))
        if index in (0, 2, 6):
            # A slim closed leaf silhouette plus a midrib, inset beyond the silk frame.
            foot = graph.position(nodes[max(2, len(nodes)//3)])
            direction = (ux * 35 + normal[0]*9, uy * 35 + normal[1]*9)
            perp = (-direction[1], direction[0])
            magnitude = math.hypot(*perp)
            tip_leaf = (foot[0] + direction[0], foot[1] + direction[1])
            left = (foot[0] + direction[0]*0.45 + perp[0]*7/magnitude,
                    foot[1] + direction[1]*0.45 + perp[1]*7/magnitude)
            right = (foot[0] + direction[0]*0.45 - perp[0]*7/magnitude,
                     foot[1] + direction[1]*0.45 - perp[1]*7/magnitude)
            origin = nodes[max(2, len(nodes)//3)]
            leaf_color = _rgb(COLORS["leaf"])
            vein_color = _rgb(COLORS["leaf_vein"])
            for path, shade in (([origin, left, tip_leaf, right, origin], leaf_color),
                                ([origin, tip_leaf], vein_color)):
                graph.add_thread(path, "LEAF", env=True,
                                 styles=[(BY_NAME["LEAF"].width, shade, 0.72)]*(len(path)-1))
    return anchors, start
