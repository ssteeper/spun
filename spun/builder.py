"""Spider agent and mutable plan graph; final thread geometry is emitted later."""

from dataclasses import dataclass, field
import heapq

from .geometry import length, point_on
from .silkfile import quantize_coord


@dataclass
class Node:
    point: tuple[float, float]
    fixed: bool = False


@dataclass
class Thread:
    kind: str
    path: list[int]
    env: bool = False
    sticky: bool = False
    live: bool = True
    styles: list[tuple[float, tuple[int, int, int], float]] | None = None
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    operation: str
    payload: object
    builder: int = 0


class PlanGraph:
    def __init__(self):
        self.nodes: list[Node] = []
        self._coordinates: dict[tuple[int, int], int] = {}
        self.threads: list[Thread] = []
        self.actions: list[Action] = []

    def node(self, point, *, fixed=False):
        coords = tuple(quantize_coord(float(x)) for x in point)
        if coords in self._coordinates:
            index = self._coordinates[coords]
            self.nodes[index].fixed |= fixed
            return index
        index = len(self.nodes)
        self.nodes.append(Node(tuple(map(float, point)), fixed))
        self._coordinates[coords] = index
        return index

    def position(self, node):
        return self.nodes[node].point

    def add_thread(self, path, kind, *, env=False, sticky=False, styles=None, builder=0, data=None):
        nodes = [p if isinstance(p, int) else self.node(p) for p in path]
        if len(nodes) < 2 or any(a == b or length(self.position(a), self.position(b)) < 0.25
                                  for a, b in zip(nodes, nodes[1:])):
            raise ValueError("a thread cannot contain a zero-length sub-segment")
        thread = len(self.threads)
        self.threads.append(Thread(kind, nodes, env, sticky, True, styles, data or {}))
        self.actions.append(Action("spin", thread, builder))
        return thread

    def attach(self, thread_id, point):
        """Split the *plan* thread; its original emission is decided only at replay."""
        thread = self.threads[thread_id]
        px, py = point
        best = None
        for i, (a, b) in enumerate(zip(thread.path, thread.path[1:])):
            p, q = self.position(a), self.position(b)
            dx, dy = q[0] - p[0], q[1] - p[1]
            t = ((px - p[0])*dx + (py - p[1])*dy) / (dx*dx + dy*dy)
            if -0.001 <= t <= 1.001:
                candidate = point_on(p, q, max(0.0, min(t, 1.0)))
                distance = length(candidate, point)
                if best is None or distance < best[0]:
                    best = distance, i, t
        if best is None or best[0] > 0.22:
            raise ValueError(f"attachment ({px:.3f}, {py:.3f}) is not on thread {thread_id}")
        _, i, t = best
        if t <= 0.001 or length(point, self.position(thread.path[i])) < 0.126:
            return thread.path[i]
        if t >= 0.999 or length(point, self.position(thread.path[i + 1])) < 0.126:
            return thread.path[i + 1]
        node = self.node(point)
        if node == thread.path[i] or node == thread.path[i + 1]:
            return node
        thread.path.insert(i + 1, node)
        return node

    def final_subpath(self, thread_id, a, b):
        nodes = self.threads[thread_id].path
        ia, ib = nodes.index(a), nodes.index(b)
        return nodes[ia:ib+1] if ia < ib else list(reversed(nodes[ib:ia+1]))


class Builder:
    def __init__(self, graph: PlanGraph, start, index=0):
        self.graph = graph
        self.current = start
        self.index = index
        self.ended = False

    def spin(self, path, kind, sticky=False, *, data=None):
        if self.ended:
            raise ValueError("builder has already rested")
        nodes = [p if isinstance(p, int) else self.graph.node(p) for p in path]
        if nodes[0] != self.current:
            raise ValueError("spin path does not start at the spinnerets")
        thread = self.graph.add_thread(nodes, kind, sticky=sticky, builder=self.index, data=data)
        self.current = nodes[-1]
        return thread

    def walk_to(self, target, *, only=None):
        if target == self.current:
            return
        graph = self.graph
        neighbours: dict[int, list[tuple[int, int, float]]] = {}
        for thread_id, thread in enumerate(graph.threads):
            if not thread.live or only is not None and thread_id not in only:
                continue
            for a, b in zip(thread.path, thread.path[1:]):
                cost = length(graph.position(a), graph.position(b))
                neighbours.setdefault(a, []).append((b, thread_id, cost))
                neighbours.setdefault(b, []).append((a, thread_id, cost))
        queue = [(0.0, self.current)]
        best = {self.current: 0.0}
        parent = {}
        while queue:
            distance, current = heapq.heappop(queue)
            if current == target:
                break
            if distance != best[current]:
                continue
            for next_node, thread_id, cost in neighbours.get(current, []):
                candidate = distance + cost
                if candidate < best.get(next_node, float("inf")) - 1e-9:
                    best[next_node] = candidate
                    parent[next_node] = (current, thread_id)
                    heapq.heappush(queue, (candidate, next_node))
        if target not in parent:
            raise ValueError(f"no live silk or scaffold path from node {self.current} to {target}")
        path = []
        node = target
        while node != self.current:
            previous, thread_id = parent[node]
            path.append((thread_id, previous, node))
            node = previous
        graph.actions.append(Action("walk", tuple(reversed(path)), self.index))
        self.current = target

    def remove(self, threads):
        for thread_id in threads:
            if not self.graph.threads[thread_id].live:
                raise ValueError("cannot remove an already eaten thread")
            self.graph.threads[thread_id].live = False
        self.graph.actions.append(Action("remove", tuple(threads), self.index))

    def rest(self, pose, angle):
        self.ended = True
        self.graph.actions.append(Action("rest", (self.current, pose, angle), self.index))
