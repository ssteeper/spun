"""Sequential orb program S1–S9, including emergent spiral turnbacks."""

from dataclasses import dataclass
import math
import zlib

import numpy as np

from .builder import Builder, PlanGraph
from .emit import emit
from .geometry import length, ray_polygon
from .pacing import pace
from .relax import relax
from .scaffold import BranchSpec, orb_scaffold
from .silkfile import write_silk
from .validate import validate


@dataclass(frozen=True)
class OrbParameters:
    id: str
    width: int
    height: int
    polygon: tuple[tuple[float, float], ...]
    radii_min: int
    radii_max: int
    hub_fraction: float
    spacing_outer: float
    spacing_inner: float
    free_radius: float
    auxiliary_spacing: float
    mm_per_px: float
    duration: float
    branches: tuple[BranchSpec, ...]
    lower_anchor: int | None = None
    pose: str = "hub-rest"
    golden: bool = False
    open_sectors: tuple[tuple[float, float], ...] = ()


@dataclass
class Ray:
    angle: float
    foot: int
    thread: int
    radius: float


@dataclass
class OrbResult:
    data: bytes
    records: np.ndarray
    beads: np.ndarray
    metadata: dict
    rest: dict
    graph: PlanGraph
    relaxation: object
    turnbacks: int
    turnback_locations: list[tuple[int, float]]
    radial_gap_cv: float
    spacing_cv: float
    env_fraction: float


def _between_open(angle, sectors):
    return any(0 < (angle-start) % math.tau < (end-start) % math.tau
               for start, end in sectors)


def _angular_gap(rays, i):
    return (rays[(i+1) % len(rays)].angle-rays[i].angle) % math.tau

def _available_sections(start, gap, sectors):
    sections = [(start, start+gap)]
    for opening, end in sectors:
        width = (end-opening) % math.tau
        for shift in (-1, 0, 1, 2):
            lower = opening+shift*math.tau
            upper = lower+width
            sections = [(a, b) for left, right in sections
                        for a, b in ((left, min(right, lower)), (max(left, upper), right))
                        if b > a]
    return sections


def _add_radii(builder, hub, polygon, seed_rays, frame_threads, target, rng, sectors):
    graph = builder.graph
    rays = sorted(seed_rays, key=lambda ray: ray.angle)
    previous_half = None
    while True:
        sections = sorted(((right-left, i, left, right)
                           for i in range(len(rays))
                           for left, right in _available_sections(
                               rays[i].angle, _angular_gap(rays, i), sectors)), reverse=True)
        if not sections or sections[0][0] <= math.tau/target:
            break
        chosen = None
        for gap, i, left_edge, right_edge in sections:
            if gap <= math.tau/target:
                break
            midpoint = (left_edge+right_edge)/2
            half = 0 if math.cos(midpoint) < 0 else 1
            if previous_half is not None and half == previous_half and any(
                    (0 if math.cos((a+b)/2) < 0 else 1) != previous_half and span > math.tau/target
                    for span, _, a, b in sections):
                continue
            for _ in range(24):
                proposed = midpoint + rng.normal(0, 0.12*gap)
                if not left_edge < proposed < right_edge:
                    continue
                angle = proposed % math.tau
                left = (angle-rays[i].angle) % math.tau
                right = (rays[(i+1) % len(rays)].angle-angle) % math.tau
                if min(left, right) >= 0.45*math.tau/len(rays):
                    chosen = i, angle, half
                    break
            if chosen is not None:
                break
        if chosen is None:
            raise ValueError("no radial candidate passes gap rejection")
        i, angle, previous_half = chosen
        distance, edge, point = ray_polygon(graph.position(hub), angle, polygon)
        foot = graph.attach(frame_threads[edge], point)
        neighbour = rays[i] if abs((angle-rays[i].angle) % math.tau) < abs((rays[(i+1)%len(rays)].angle-angle) % math.tau) else rays[(i+1)%len(rays)]
        builder.walk_to(hub)
        builder.walk_to(neighbour.foot, only=(neighbour.thread,))
        builder.walk_to(foot, only=frame_threads)
        thread = builder.spin([foot, hub], "RADIUS")
        rays.append(Ray(angle, foot, thread, distance))
        rays.sort(key=lambda ray: ray.angle)
        if len(rays) > 2*target:
            raise ValueError("largest-gap radius rule exceeded twice its target")
    return rays


def _ray_junction(graph, ray, hub, distance):
    origin = graph.position(hub)
    destination = graph.position(ray.foot)
    span = length(origin, destination)
    if not 0 < distance < span:
        raise ValueError("radial junction lies outside its spoke")
    return graph.attach(ray.thread, (origin[0]+distance/span*(destination[0]-origin[0]),
                                     origin[1]+distance/span*(destination[1]-origin[1])))


def _hub(builder, rays, hub, free_radius):
    graph = builder.graph
    for distance in np.linspace(8, 0.45*free_radius, 3):
        nodes = [_ray_junction(graph, ray, hub, float(distance)) for ray in rays]
        for j, start in enumerate(nodes):
            builder.walk_to(start)
            builder.spin([start, nodes[(j+1) % len(rays)]], "HUB")
    builder.walk_to(hub)


def _spiral(builder, rays, hub, *, inward, r_free, aux_spacing, inner, outer,
            rng, sectors, auxiliaries=()):
    graph = builder.graph
    n = len(rays)
    limits = [r_free if inward else 0.90*ray.radius for ray in rays]
    first = [0.94*ray.radius if inward else 0.45*r_free+8 for ray in rays]
    frontiers = first.copy()
    index, direction = 0, 1
    current = _ray_junction(graph, rays[index], hub, frontiers[index])
    builder.walk_to(current)
    visits = [0]*n
    visits[index] = 1
    turnbacks = 0
    turnback_locations = []
    laid = []
    remaining_aux = dict(auxiliaries)
    blocked = set()
    for _ in range(50000):
        base_spacing = (inner+(outer-inner)*frontiers[index]/rays[index].radius
                        if inward else aux_spacing)
        step = max(0.25, base_spacing*(1+rng.normal(0, 0.08)) if inward else base_spacing)

        def candidate(neighbour):
            angle0, angle1 = rays[index].angle, rays[neighbour].angle
            arc = ((angle1-angle0) if direction == 1 else (angle0-angle1)) % math.tau
            def along(theta):
                return ((theta-angle0) if direction == 1 else (angle0-theta)) % math.tau
            across = any(_between_open(angle0, ((start, end),)) or
                         _between_open(angle1, ((start, end),)) or
                         0 < along((start+(end-start) % math.tau/2) % math.tau) < arc
                         for start, end in sectors)
            if across:
                return None
            radial = (first[neighbour] if visits[neighbour] == 0 else
                      frontiers[neighbour] - step if inward else frontiers[neighbour] + step)
            if inward and radial <= limits[neighbour]:
                if frontiers[neighbour]-limits[neighbour] <= 0.5:
                    return None
                radial = limits[neighbour]+0.5
            elif not inward and radial >= limits[neighbour]:
                return None
            return radial

        neighbour = (index+direction) % n
        radius = candidate(neighbour)
        if radius is None:
            direction = -direction
            neighbour = (index+direction) % n
            radius = candidate(neighbour)
            if radius is not None:
                turnbacks += 1
                turnback_locations.append((visits[index]-1, round(math.degrees(rays[index].angle), 1)))
        if radius is None:
            blocked.add(index)
            room = [(f-r_free if inward else lim-f, j)
                    for j, (f, lim) in enumerate(zip(frontiers, limits))
                    if j not in blocked]
            if not room:
                break
            available, j = max(room)
            if available < 2*step:
                break
            index = j
            current = _ray_junction(graph, rays[index], hub, frontiers[index])
            builder.walk_to(current)
            continue
        end = _ray_junction(graph, rays[neighbour], hub, radius)
        thread = builder.spin([current, end], "CAPTURE" if inward else "AUX",
                              sticky=inward, data={"spokes": (index, neighbour),
                                                   "distances": (frontiers[index], radius)})
        if not inward:
            laid.append((thread, index, frontiers[index], neighbour, radius))
        frontiers[neighbour] = radius
        visits[neighbour] += 1
        index, current = neighbour, end
        if inward and remaining_aux:
            eaten = [thread_id for thread_id, (j, a, k, b) in remaining_aux.items()
                     if frontiers[j] <= a-step/2 and frontiers[k] <= b-step/2]
            if eaten:
                builder.remove(eaten)
                for thread_id in eaten:
                    del remaining_aux[thread_id]
    else:
        raise ValueError("spiral frontier failed to terminate")
    return laid, turnbacks, list(remaining_aux), turnback_locations


def build_orb(spec: OrbParameters):
    seed = zlib.crc32(spec.id.encode("utf-8"))
    rng = np.random.default_rng(seed)
    bark_rng = np.random.default_rng(seed ^ 0x9E3779B9)
    graph = PlanGraph()
    anchors, first = orb_scaffold(graph, spec.polygon, bark_rng, spec.branches)
    builder = Builder(graph, first)
    builder.walk_to(anchors[0])
    bridge = builder.spin([anchors[0], anchors[1]], "BRIDGE")
    a, b = spec.polygon[0], spec.polygon[1]
    fraction = rng.uniform(0.4, 0.6)
    m = graph.attach(bridge, (a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1])))
    top, bottom = min(p[1] for p in spec.polygon), max(p[1] for p in spec.polygon)
    hub = graph.node((graph.position(m)[0]+rng.uniform(-16, 16),
                      top+spec.hub_fraction*(bottom-top)))
    bottom_anchor = spec.lower_anchor if spec.lower_anchor is not None else len(anchors)//2
    builder.walk_to(m)
    seed = builder.spin([m, hub, anchors[bottom_anchor]], "RADIUS")
    builder.walk_to(anchors[1])
    right = builder.spin(anchors[1:bottom_anchor+1], "FRAME")
    left = builder.spin(anchors[bottom_anchor:]+[anchors[0]], "FRAME")
    frame_threads = (bridge, right, left)
    # Each frame edge belongs to one of the three spun polygon paths.
    edge_threads = (bridge,) + (right,)*(bottom_anchor-1) + (left,)*(len(anchors)-bottom_anchor)
    builder.walk_to(hub)
    seed_rays = [Ray(math.atan2(graph.position(foot)[1]-graph.position(hub)[1],
                              graph.position(foot)[0]-graph.position(hub)[0]) % math.tau,
                     foot, seed, length(graph.position(hub), graph.position(foot)))
                 for foot in (m, anchors[bottom_anchor])]
    target = int(rng.integers(spec.radii_min, spec.radii_max+1))
    rays = _add_radii(builder, hub, spec.polygon, seed_rays, edge_threads,
                     target, rng, spec.open_sectors)
    builder.walk_to(hub)
    _hub(builder, rays, hub, spec.free_radius)
    auxiliary, _, _, _ = _spiral(builder, rays, hub, inward=False, r_free=spec.free_radius,
                              aux_spacing=spec.auxiliary_spacing, inner=spec.spacing_inner,
                              outer=spec.spacing_outer, rng=rng, sectors=spec.open_sectors)
    _, turnbacks, residual, turnback_locations = _spiral(builder, rays, hub, inward=True,
                                     r_free=spec.free_radius, aux_spacing=spec.auxiliary_spacing,
                                     inner=spec.spacing_inner, outer=spec.spacing_outer,
                                     rng=rng, sectors=spec.open_sectors,
                                     auxiliaries=({thread: (j, a, k, b)
                                                   for thread, j, a, k, b in auxiliary}
                                                  if not spec.golden else {}))
    if residual and not spec.golden:
        builder.remove(residual)
    builder.walk_to(hub)
    builder.rest(spec.pose, math.pi/2)
    radial_paths = [graph.final_subpath(ray.thread, hub, ray.foot) for ray in rays]
    relaxation = relax(graph, radial_paths, float(np.mean([ray.radius for ray in rays])))
    records, beads, rest = emit(graph)
    data = write_silk(spec.width, spec.height, 1, records, beads)
    timing = pace(records, spec.duration)
    frame = [list(graph.position(anchor)) for anchor in anchors]
    ray_ends = [list(graph.position(ray.foot)) for ray in rays]
    metadata = {"kind": "orb", "golden": spec.golden,
                "orbs": [{"builder": 0, "hub": list(graph.position(hub)),
                          "frame": frame, "radii": ray_ends,
                          "openSectors": [list(s) for s in spec.open_sectors]}],
                "timeline": timing["timeline"], "stages": timing["stages"],
                "rests": {0: (rest[0]["x"], rest[0]["y"])},
                "catalogueBytes": len(data), "indexBytes": 0,
                "defaultBytes": len(data)}
    validate(data, metadata)
    angles = sorted(ray.angle for ray in rays)
    gaps = [(angles[(i+1)%len(angles)]-angle) % math.tau for i, angle in enumerate(angles)]
    radial_gap_cv = float(np.std(gaps)/np.mean(gaps))
    # Measure successive junction gaps on every spoke after quantization.
    junctions = [[] for _ in rays]
    origin = np.array(graph.position(hub))
    for thread in graph.threads:
        if thread.kind != "CAPTURE":
            continue
        for spoke, node in zip(thread.data["spokes"], (thread.path[0], thread.path[-1])):
            point = np.rint(np.array(graph.position(node))*4)/4
            junctions[spoke].append(float(np.linalg.norm(point-origin)))
    spacing = []
    for values in junctions:
        ordered = sorted(values)
        distinct = []
        for value in ordered:
            if not distinct or value-distinct[-1] > 0.26:
                distinct.append(value)
        spacing.extend(b-a for a, b in zip(distinct, distinct[1:]))
    spacing_cv = float(np.std(spacing)/np.mean(spacing))
    return OrbResult(data, records, beads, metadata, rest, graph, relaxation,
                     turnbacks, turnback_locations, radial_gap_cv, spacing_cv, timing["envFraction"])
