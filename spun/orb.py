"""Sequential orb program S1–S9, including emergent spiral turnbacks."""

from dataclasses import dataclass
from typing import Callable
import math
import zlib

import numpy as np

from .builder import Builder, PlanGraph
from .emit import emit
from .kinds import BY_NAME, COLORS
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
    extra: Callable | None = None
    # Colony only: frame corners that sit on an earlier orb's live frame thread.
    shared: tuple[int, ...] = ()


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
    width: int
    height: int
    builder_count: int


@dataclass
class OrbPlan:
    spec: OrbParameters
    builder_index: int
    anchors: list[int]
    hub: int
    rays: list[Ray]
    frame_threads: tuple[int, ...]
    turnbacks: int
    turnback_locations: list[tuple[int, float]]


# Largest radial drop, in units of the chord's arc length, that an inward row
# accepts onto an already-visited neighbour before she turns back.
SLANT = 0.5


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
    """Attach at ``distance`` on the spoke, reusing a node closer than 1 px.

    Sub-pixel radial stubs between two nearly coincident junctions quantize
    into false crossings, so near neighbours share one knot instead.
    """
    origin = graph.position(hub)
    destination = graph.position(ray.foot)
    span = length(origin, destination)
    if not 0 < distance < span:
        raise ValueError("radial junction lies outside its spoke")
    for node in graph.final_subpath(ray.thread, hub, ray.foot)[1:]:
        if node != hub and abs(length(origin, graph.position(node))-distance) < 1.0:
            return node
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

    def candidate(origin, neighbour, heading, step):
        angle0, angle1 = rays[origin].angle, rays[neighbour].angle
        arc = ((angle1-angle0) if heading == 1 else (angle0-angle1)) % math.tau

        def along(theta):
            return ((theta-angle0) if heading == 1 else (angle0-theta)) % math.tau
        across = any(_between_open(angle0, ((start, end),)) or
                     _between_open(angle1, ((start, end),)) or
                     0 < along((start+(end-start) % math.tau/2) % math.tau) < arc
                     for start, end in sectors)
        if across:
            return None
        radial = (first[neighbour] if visits[neighbour] == 0 else
                  frontiers[neighbour] - step if inward else frontiers[neighbour] + step)
        if inward and radial <= limits[neighbour]:
            if frontiers[neighbour]-limits[neighbour] < 0.5*step:
                return None
            radial = limits[neighbour]+0.5
        elif not inward and radial >= limits[neighbour]:
            return None
        # A neighbour whose row already lies deeper than her own level by more
        # than the chord's arc has no room *here*; she turns back and the deep
        # side of the web gains the extra rows (emergent turnbacks).
        if (inward and visits[neighbour] and
                frontiers[origin]-radial > max(step, SLANT*radial*arc)):
            return None
        return radial

    for _ in range(50000):
        base_spacing = (inner+(outer-inner)*frontiers[index]/rays[index].radius
                        if inward else aux_spacing)
        step = max(0.25, base_spacing*(1+rng.normal(0, 0.08)) if inward else base_spacing)
        neighbour = (index+direction) % n
        radius = candidate(index, neighbour, direction, step)
        if radius is None:
            neighbour = (index-direction) % n
            radius = candidate(index, neighbour, -direction, step)
            if radius is not None:
                direction = -direction
                turnbacks += 1
                turnback_locations.append((visits[index]-1, round(math.degrees(rays[index].angle), 1)))
        if radius is None:
            # Only spokes from which a chord can actually leave are jump targets.
            room = [(f-r_free if inward else lim-f, j)
                    for j, (f, lim) in enumerate(zip(frontiers, limits))
                    if j != index and any(candidate(j, (j+h) % n, h, step) is not None
                                          for h in (1, -1))]
            if not room:
                break
            available, j = max(room)
            if available < 2*step:
                break
            index = j
            # Her junction on a jumped-to spoke counts as its first visit.
            visits[index] = max(visits[index], 1)
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


def _plan_orb(spec: OrbParameters, graph: PlanGraph, anchors: list[int],
              first: int, builder_index: int) -> OrbPlan:
    rng = np.random.default_rng(zlib.crc32(spec.id.encode("utf-8")))
    builder = Builder(graph, first, index=builder_index)
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
    _, turnbacks, residual, turnback_locations = _spiral(
        builder, rays, hub, inward=True, r_free=spec.free_radius,
        aux_spacing=spec.auxiliary_spacing, inner=spec.spacing_inner,
        outer=spec.spacing_outer, rng=rng, sectors=spec.open_sectors,
        auxiliaries=({thread: (j, a, k, b) for thread, j, a, k, b in auxiliary}
                     if not spec.golden else {}))
    if residual and not spec.golden:
        builder.remove(residual)
    builder.walk_to(hub)
    rest_node = (spec.extra(builder, rays, hub, anchors, rng, spec, frame_threads)
                 if spec.extra else None)
    builder.walk_to(hub if rest_node is None else rest_node)
    builder.rest(spec.pose, math.pi/2)
    if spec.golden:
        palette = {"BRIDGE": "golden_frame", "FRAME": "golden_frame",
                   "RADIUS": "golden_radius", "CAPTURE": "golden_capture",
                   "AUX": "golden_aux"}
        for action in graph.actions:
            if action.operation != "spin" or action.builder != builder_index:
                continue
            thread = graph.threads[action.payload]
            if thread.kind in palette:
                color = tuple(bytes.fromhex(COLORS[palette[thread.kind]][1:]))
                kind = BY_NAME[thread.kind]
                alpha = 0.32 if thread.kind == "AUX" else kind.alpha
                thread.styles = [(kind.width, color, alpha)]*(len(thread.path)-1)
    return OrbPlan(spec, builder_index, anchors, hub, rays, frame_threads,
                   turnbacks, turnback_locations)


def _orb_metrics(graph: PlanGraph, plan: OrbPlan) -> tuple[float, float]:
    rays = plan.rays
    gaps = [(rays[(i+1) % len(rays)].angle-ray.angle) % math.tau
            for i, ray in enumerate(rays)]
    # As the validator: gaps bordering an open sector are excluded from the CV.
    gaps = [gap for ray, gap in zip(rays, gaps)
            if not any(0 <= (edge-ray.angle) % math.tau < gap
                       for sector in plan.spec.open_sectors for edge in sector)]
    junctions = [[] for _ in rays]
    origin = np.array(graph.position(plan.hub))
    for action in graph.actions:
        if action.operation != "spin" or action.builder != plan.builder_index:
            continue
        thread = graph.threads[action.payload]
        if thread.kind != "CAPTURE":
            continue
        for spoke, node in zip(thread.data["spokes"], (thread.path[0], thread.path[-1])):
            point = np.rint(np.array(graph.position(node))*4)/4
            junctions[spoke].append(float(np.linalg.norm(point-origin)))
    spacing = []
    for values in junctions:
        distinct = []
        for value in sorted(values):
            if not distinct or value-distinct[-1] > 0.26:
                distinct.append(value)
        spacing.extend(b-a for a, b in zip(distinct, distinct[1:]))
    return float(np.std(gaps)/np.mean(gaps)), float(np.std(spacing)/np.mean(spacing))


def _finish_orbs(specs: tuple[OrbParameters, ...], graph: PlanGraph,
                 plans: list[OrbPlan]) -> OrbResult:
    radial_paths = [graph.final_subpath(ray.thread, plan.hub, ray.foot)
                    for plan in plans for ray in plan.rays]
    mean_radius = float(np.mean([ray.radius for plan in plans for ray in plan.rays]))
    relaxation = relax(graph, radial_paths, mean_radius)
    records, beads, rest = emit(graph)
    data = write_silk(specs[0].width, specs[0].height, len(plans), records, beads)
    timing = pace(records, specs[0].duration)
    metrics = [_orb_metrics(graph, plan) for plan in plans]
    metadata = {
        "kind": "orb", "golden": specs[0].golden, "anchor": list(graph.position(plans[0].hub)), "mmPerUnit": specs[0].mm_per_px,
        "orbs": [{"builder": plan.builder_index, "hub": list(graph.position(plan.hub)),
                  "frame": [list(graph.position(anchor)) for anchor in plan.anchors],
                  "radii": [list(graph.position(ray.foot)) for ray in plan.rays],
                  "openSectors": [list(s) for s in plan.spec.open_sectors],
                  "radialGapCV": metrics[i][0], "spacingCV": metrics[i][1],
                  "turnbacks": plan.turnbacks}
                 for i, plan in enumerate(plans)],
        "timeline": timing["timeline"], "stages": timing["stages"],
        "rests": {i: (pose["x"], pose["y"]) for i, pose in rest.items()},
        "catalogueBytes": len(data), "indexBytes": 0,
        "defaultBytes": len(data) if specs[0].id == "st-andrews-cross" else 0,
    }
    validate(data, metadata)
    return OrbResult(data, records, beads, metadata, rest, graph, relaxation,
                     sum(plan.turnbacks for plan in plans),
                     [location for plan in plans for location in plan.turnback_locations],
                     float(np.mean([pair[0] for pair in metrics])),
                     float(np.mean([pair[1] for pair in metrics])),
                     timing["envFraction"], specs[0].width, specs[0].height, len(plans))


def build_orb(spec: OrbParameters) -> OrbResult:
    graph = PlanGraph()
    seed = zlib.crc32(spec.id.encode("utf-8"))
    anchors, first = orb_scaffold(
        graph, spec.polygon, np.random.default_rng(seed ^ 0x9E3779B9), spec.branches)
    plan = _plan_orb(spec, graph, anchors, first, 0)
    return _finish_orbs((spec,), graph, [plan])


def build_colony(specs: tuple[OrbParameters, ...]) -> OrbResult:
    """Build all scaffold first, then each orb sequentially on one pre-split graph.

    A later orb's ``shared`` frame corners attach to an earlier orb's live
    frame thread, splitting it in the plan graph only.
    """
    if len(specs) != 3 or specs[0].shared or not all(spec.shared for spec in specs[1:]):
        raise ValueError("the colony needs three sequential orbs, the later two sharing frames")
    graph = PlanGraph()
    scaffold = []
    for spec in specs:
        seed = zlib.crc32(spec.id.encode("utf-8"))
        scaffold.append(orb_scaffold(
            graph, spec.polygon, np.random.default_rng(seed ^ 0x9E3779B9), spec.branches,
            shared=spec.shared))
    plans = []
    for index, (spec, (anchors, first)) in enumerate(zip(specs, scaffold)):
        for anchor_index in spec.shared:
            point = spec.polygon[anchor_index]
            attached = None
            for previous in plans:
                for frame in previous.frame_threads:
                    try:
                        attached = graph.attach(frame, point)
                    except ValueError:
                        continue
                    break
                if attached is not None:
                    break
            if attached is None:
                raise ValueError("shared colony anchor must lie on an earlier live frame")
            anchors[anchor_index] = attached
        plans.append(_plan_orb(spec, graph, anchors, first, index))
    return _finish_orbs(specs, graph, plans)
