"""Behavioral invariants for the reference species and plan/emit cutover."""

import hashlib

import numpy as np
import pytest

from species.hortophora import build
from spun.builder import Builder, PlanGraph
from spun.emit import emit
from spun.relax import relax
from spun.kinds import BY_NAME, ENV, INVISIBLE
from spun.silkfile import NEVER, read_silk
from spun.validate import validate


@pytest.fixture(scope="module")
def reference():
    return build()


def test_future_attachment_presplits_earlier_silk_and_walk():
    graph = PlanGraph()
    anchor = graph.node((0, 0), fixed=True)
    tip = graph.node((10, 0), fixed=True)
    graph.add_thread([anchor, tip], "SCAFFOLD", env=True)
    spider = Builder(graph, anchor)
    spider.walk_to(tip)
    end = graph.node((20, 0))
    silk = spider.spin([tip, end], "FRAME")
    spider.walk_to(tip)
    graph.attach(silk, (15, 0))
    spider.rest("hub-rest", 0)
    rows, _, rest = emit(graph)
    thread = rows[rows["kind"] == BY_NAME["FRAME"].id]
    walks = rows[rows["kind"] == BY_NAME["WALK"].id]
    assert [(int(r["x0"]), int(r["x1"])) for r in thread] == [(40, 60), (60, 80)]
    assert [(int(r["x0"]), int(r["x1"])) for r in walks] == [(0, 40), (80, 60), (60, 40)]
    assert rest[0]["x"] == 10


def test_no_live_graph_path_raises_instead_of_teleporting():
    graph = PlanGraph()
    first, second = graph.node((0, 0)), graph.node((10, 10))
    with pytest.raises(ValueError, match="no live silk or scaffold path"):
        Builder(graph, first).walk_to(second)

def test_rejected_relaxation_keeps_original_plan_coordinates():
    graph = PlanGraph()
    a = graph.node((0, 0), fixed=True)
    b = graph.node((10, 0))
    c = graph.node((25, 0), fixed=True)
    graph.add_thread([a, b, c], "FRAME")
    before = [node.point for node in graph.nodes]
    result = relax(graph, [[a, b, c]], mean_radius=1)
    assert not result.accepted
    assert result.max_displacement > 0.03
    assert [node.point for node in graph.nodes] == before


def test_reference_species_decoded_invariants(reference):
    silk = validate(reference.data, reference.metadata)
    assert silk.records.dtype == reference.records.dtype
    assert silk.builder_count == 1
    assert len(reference.metadata["timeline"]) == 512
    assert reference.env_fraction <= 0.08
    assert 0.08 <= reference.radial_gap_cv <= 0.40
    assert 0.05 <= reference.spacing_cv <= 0.35
    assert reference.relaxation.accepted
    assert reference.relaxation.iterations <= 400
    assert reference.turnbacks > 0


def test_temporary_silk_eaten_and_later_walks_on_live_hosts(reference):
    rows = read_silk(reference.data).records
    aux = rows[rows["kind"] == BY_NAME["AUX"].id]
    capture = rows[rows["kind"] == BY_NAME["CAPTURE"].id]
    assert len(aux) > 0 and len(capture) > 0
    assert np.all(aux["death"] != NEVER)
    assert np.all(aux["death"] > np.flatnonzero(rows["kind"] == BY_NAME["AUX"].id))
    assert not np.any(rows[(rows["flags"] & INVISIBLE) != 0]["flags"] & ENV)
    # The last record is an actual homeward walk and the rest point is its tip.
    assert rows[-1]["kind"] == BY_NAME["WALK"].id
    rest = reference.metadata["rests"][0]
    assert (int(rows[-1]["x1"]), int(rows[-1]["y1"])) == (
        round(rest[0]*4), round(rest[1]*4))


def test_two_complete_reference_builds_are_byte_identical(reference):
    another = build()
    assert hashlib.sha256(reference.data).digest() == hashlib.sha256(another.data).digest()
    assert reference.metadata["timeline"] == another.metadata["timeline"]
