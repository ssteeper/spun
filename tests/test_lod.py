"""LOD importance (§4.9): rows thin evenly; structure never drops."""

import numpy as np
import pytest

from species import SPECIES
from spun.emit import lods
from spun.kinds import BY_NAME


def min_lod(detail):
    """The viewer's threshold, for reference (§4.9)."""
    return 0 if detail >= 0.9 else round(255*(1 - detail/0.9))


STRUCTURAL = ("SCAFFOLD", "LEAF", "BRIDGE", "FRAME", "RADIUS", "HUB", "STABILIMENTUM",
              "EGGSAC", "GUMFOOT", "BOLAS", "RETREAT")


@pytest.fixture(scope="module", params=sorted(SPECIES))
def built(request):
    return request.param, SPECIES[request.param]()


def test_structural_kinds_never_drop(built):
    _, result = built
    rows = result.records
    for name in STRUCTURAL:
        assert np.all(rows["lod"][rows["kind"] == BY_NAME[name].id] == 255), name
    assert np.all(rows["lod"][rows["kind"] == BY_NAME["AUX"].id] == 128)
    assert np.all(rows["lod"][rows["kind"] == BY_NAME["TUFT"].id] == 96)
    tangle = rows["lod"][rows["kind"] == BY_NAME["TANGLE"].id]
    if len(tangle):
        assert tangle.min() == 40 and tangle.max() == 255


def _row_lods(result, kind):
    """Per builder: lod of each capture row, ordered from the rim (row 0) inward."""
    graph = result.graph
    builders = {a.payload: a.builder for a in graph.actions if a.operation == "spin"}
    importance = lods(graph)
    rows = {}
    for thread_id, thread in enumerate(graph.threads):
        if thread.kind == kind:
            rows.setdefault(builders[thread_id], []).append(
                (thread.data["level"], importance[thread_id]))
    return rows


@pytest.mark.parametrize("name", ["garden-orb-weaver", "golden-orb-weaver",
                                  "christmas-jewel-spider", "net-casting-spider"])
def test_rows_have_distinct_lods_and_thin_evenly_from_rim_to_hub(name):
    result = SPECIES[name]()
    kind = "CRIBELLATE" if name == "net-casting-spider" else "CAPTURE"
    for chords in _row_lods(result, kind).values():
        distinct = sorted({lod for _, lod in chords}, reverse=True)
        assert len(distinct) >= 15
        # Each LOD value is one row: its chords share (almost) one level.
        levels = {lod: np.median([lv for lv, l in chords if l == lod]) for lod in distinct}
        ordered = sorted(distinct, key=lambda lod: -levels[lod])  # rim → hub
        threshold = min_lod(0.45)  # 128: half detail
        kept = [lod >= threshold for lod in ordered]
        assert 0.4 <= np.mean(kept) <= 0.6
        # Survivors alternate: never more than two dropped rows in a row, anywhere.
        run = longest = 0
        for survived in kept:
            run = 0 if survived else run + 1
            longest = max(longest, run)
        assert longest <= 2
        # Spread from rim to hub: survivors in every quarter of the row sequence.
        for quarter in np.array_split(np.array(kept), 4):
            assert quarter.mean() >= 0.3
        # Rim-most row kept at any detail; the full set only at detail >= 0.9.
        assert max(distinct) == 255 and min_lod(0.9) == 0
