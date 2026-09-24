"""Every registered orb validates, keeps its signature and rebuilds byte-identically."""

import hashlib
import math

import numpy as np
import pytest

from species import SPECIES
from spun.kinds import BUILDER_MASK, BUILDER_SHIFT, BY_NAME, ENV
from spun.silkfile import NEVER, read_silk
from spun.validate import validate


@pytest.fixture(scope="module", params=sorted(SPECIES))
def built(request):
    return request.param, SPECIES[request.param]()


def test_species_passes_validator(built):
    _, result = built
    validate(result.data, result.metadata)
    # Snares are laid at their held/hanging positions and are never relaxed.
    assert result.relaxation.accepted if result.metadata["kind"] == "orb" else result.relaxation is None


def test_only_the_leaf_curler_hauls_a_leaf(built):
    name, result = built
    labels = [stage["label"] for stage in result.metadata["stages"]]
    if name == "leaf-curling-spider":
        assert "hauling a leaf" in labels
        return
    assert "hauling a leaf" not in labels and labels[0] == "scaffold"
    if result.metadata["kind"] == "orb":
        assert labels[1] == "bridge line"


def test_species_rebuild_is_byte_identical(built):
    name, result = built
    again = SPECIES[name]()
    assert hashlib.sha256(result.data).digest() == hashlib.sha256(again.data).digest()
    assert result.metadata["timeline"] == again.metadata["timeline"]


def test_golden_retains_temporary_spiral_and_turns_back_below_high_hub():
    result = SPECIES["golden-orb-weaver"]()
    rows = read_silk(result.data).records
    aux = rows[rows["kind"] == BY_NAME["AUX"].id]
    assert len(aux) and np.all(aux["death"] == NEVER)
    orb = result.metadata["orbs"][0]
    ys = [y for _, y in orb["frame"]]
    assert (orb["hub"][1]-min(ys))/(max(ys)-min(ys)) <= 0.4
    assert orb["turnbacks"] >= 6
    # The tangle curtain spans the 0.35–0.6 depth alpha range.
    tangle = rows[rows["kind"] == BY_NAME["TANGLE"].id]
    assert 40 <= len(tangle) and 89 <= tangle["alpha"].min() < tangle["alpha"].max() <= 153


def test_argiope_bands_start_and_end_on_their_radii():
    result = SPECIES["st-andrews-cross"]()
    rows = read_silk(result.data).records
    kinds = rows["kind"]
    band = kinds == BY_NAME["STABILIMENTUM"].id
    starts = np.flatnonzero(band & ~np.roll(band, 1))
    ends = np.flatnonzero(band & ~np.roll(band, -1))
    assert len(starts) == 4
    radial = rows[kinds == BY_NAME["RADIUS"].id]
    nodes = {(int(r["x0"]), int(r["y0"])) for r in radial} | {(int(r["x1"]), int(r["y1"])) for r in radial}
    for first, last in zip(starts, ends):
        assert (int(rows[first]["x0"]), int(rows[first]["y0"])) in nodes
        assert (int(rows[last]["x1"]), int(rows[last]["y1"])) in nodes
    aux = rows[kinds == BY_NAME["AUX"].id]
    assert np.all(aux["death"] != NEVER)


def _nodes(rows, kind):
    chosen = rows[rows["kind"] == BY_NAME[kind].id]
    return ({(int(r["x0"]), int(r["y0"])) for r in chosen} |
            {(int(r["x1"]), int(r["y1"])) for r in chosen})


def _runs(rows, kind):
    mask = rows["kind"] == BY_NAME[kind].id
    starts = np.flatnonzero(mask & ~np.concatenate(([False], mask[:-1])))
    ends = np.flatnonzero(mask & ~np.concatenate((mask[1:], [False])))
    return list(zip(starts, ends))


def test_phonognatha_hauls_leaf_after_capture_and_binds_it():
    rows = read_silk(SPECIES["leaf-curling-spider"]().data).records
    kinds = rows["kind"]
    last_capture = np.flatnonzero(kinds == BY_NAME["CAPTURE"].id).max()
    late_leaf = np.flatnonzero(kinds == BY_NAME["LEAF"].id)
    late_leaf = late_leaf[late_leaf > last_capture]
    assert len(late_leaf) > 20 and np.all(rows["flags"][late_leaf] & ENV)
    stitches = rows[kinds == BY_NAME["RETREAT"].id]
    assert 6 <= len(stitches) <= 10
    radial = _nodes(rows, "RADIUS")
    assert all((int(r["x0"]), int(r["y0"])) in radial for r in stitches)


def test_austracantha_three_builders_share_frames_and_tuft_every_20mm():
    result = SPECIES["christmas-jewel-spider"]()
    rows = read_silk(result.data).records
    builders = (rows["flags"] & BUILDER_MASK) >> BUILDER_SHIFT
    assert result.builder_count == 3
    silk = (rows["flags"] & ENV) == 0
    order = builders[silk]
    assert list(order) == sorted(order)
    for later in (1, 2):
        earlier = rows[(rows["kind"] == BY_NAME["FRAME"].id) & (builders < later)]
        earlier_nodes = ({(int(r["x0"]), int(r["y0"])) for r in earlier} |
                         {(int(r["x1"]), int(r["y1"])) for r in earlier})
        own = rows[(rows["kind"] == BY_NAME["FRAME"].id) & (builders == later)]
        assert any((int(r["x0"]), int(r["y0"])) in earlier_nodes for r in own)
    spacing_px = 20/result.metadata["mmPerUnit"]
    for builder in range(3):
        tufts = [(s, e) for s, e in _runs(rows, "TUFT") if builders[s] == builder]
        assert len(tufts) >= 8
        for s, e in tufts:
            span = rows[s:e+1]
            dx = span["x1"].astype(float)-span["x0"]
            dy = span["y1"].astype(float)-span["y0"]
            total = float(np.sum(np.hypot(dx, dy)))/4
            assert 6 <= e-s+1 <= 10 and 5.5 <= total <= 12.5
        gaps = [np.hypot(int(rows[b]["x0"])-int(rows[a]["x0"]),
                         int(rows[b]["y0"])-int(rows[a]["y0"]))/4
                for (a, _), (b, _) in zip(tufts, tufts[1:])]
        assert 0.75*spacing_px <= float(np.median(gaps)) <= 1.25*spacing_px


def test_arachnura_open_sector_has_one_signal_line_and_a_string_of_sacs():
    result = SPECIES["scorpion-tailed-spider"]()
    rows = read_silk(result.data).records
    orb = result.metadata["orbs"][0]
    hub = orb["hub"]
    (start, end), = orb["openSectors"]
    inside = [foot for foot in orb["radii"]
              if 0 < (math.atan2(foot[1]-hub[1], foot[0]-hub[0])-start) % math.tau
              < (end-start) % math.tau]
    assert len(inside) == 1
    radial = _nodes(rows, "RADIUS")
    sacs = [r for r in rows[rows["kind"] == BY_NAME["EGGSAC"].id]
            if (int(r["x0"]), int(r["y0"])) in radial]
    assert 5 <= len(sacs) <= 8
    assert result.rest[0]["pose"] == "hub-tail"
