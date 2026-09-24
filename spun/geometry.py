"""Small planar geometry primitives used by planning, scaffolding and relaxation."""

import math

import numpy as np


def length(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def point_on(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def ray_polygon(hub, angle, polygon):
    """Return the nearest positive ray/polygon intersection and its edge index."""
    ux, uy = math.cos(angle), math.sin(angle)
    nearest = None
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        determinant = ux * dy - uy * dx
        if abs(determinant) < 1e-9:
            continue
        vx, vy = a[0] - hub[0], a[1] - hub[1]
        distance = (vx * dy - vy * dx) / determinant
        fraction = (vx * uy - vy * ux) / determinant
        if distance > 0 and -1e-8 <= fraction <= 1 + 1e-8 and (nearest is None or distance < nearest[0]):
            nearest = (distance, i, (hub[0] + ux * distance, hub[1] + uy * distance))
    if nearest is None:
        raise ValueError("orb radius does not hit frame polygon")
    return nearest


def catmull_rom(controls, interval=8.0):
    """Centripetal Catmull–Rom twig sampled at approximately interval pixels."""
    if len(controls) < 4:
        raise ValueError("a twig needs at least four control points")
    points = [tuple(map(float, controls[0]))]
    for i in range(len(controls) - 1):
        p0, p1 = np.array(controls[max(i - 1, 0)], float), np.array(controls[i], float)
        p2, p3 = np.array(controls[i + 1], float), np.array(controls[min(i + 2, len(controls) - 1)], float)
        # Hermite form of the centripetal Catmull–Rom tangent.
        d0 = max(float(np.linalg.norm(p1 - p0)), 1e-6) ** 0.5
        d1 = max(float(np.linalg.norm(p2 - p1)), 1e-6) ** 0.5
        d2 = max(float(np.linalg.norm(p3 - p2)), 1e-6) ** 0.5
        m1 = (p2 - p1) / d1 - (p2 - p0) / (d0 + d1) + (p1 - p0) / d0
        m2 = (p3 - p2) / d2 - (p3 - p1) / (d1 + d2) + (p2 - p1) / d1
        m1 *= d1
        m2 *= d1
        samples = max(1, math.ceil(float(np.linalg.norm(p2 - p1)) / interval))
        for j in range(1, samples + 1):
            t = j / samples
            position = ((2*t**3-3*t**2+1)*p1 + (t**3-2*t**2+t)*m1 +
                        (-2*t**3+3*t**2)*p2 + (t**3-t**2)*m2)
            points.append((float(position[0]), float(position[1])))
    return points


def segment_crosses(a, b, c, d):
    """Proper intersection, excluding shared endpoints and collinear neighbours."""
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    if a == c or a == d or b == c or b == d:
        return False
    return cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0
