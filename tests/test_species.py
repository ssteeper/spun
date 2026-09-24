"""Every registered orb validates, keeps its signature and rebuilds byte-identically."""

import hashlib

import numpy as np
import pytest

from species import SPECIES
from spun.kinds import BY_NAME
from spun.silkfile import NEVER, read_silk
from spun.validate import validate


@pytest.fixture(scope="module", params=sorted(SPECIES))
def built(request):
    return request.param, SPECIES[request.param]()


def test_species_passes_validator(built):
    _, result = built
    validate(result.data, result.metadata)
    assert result.relaxation.accepted


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
