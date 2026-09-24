"""Snare signatures: the held net, the bolas through leg II, the split gumfoot lines."""

import math

import numpy as np
import pytest

from species import BY_ID, SPECIES
from spun.kinds import BY_NAME, ENV, STICKY
from spun.spider import rest_points_px


def _runs(rows, kind):
    mask = rows["kind"] == BY_NAME[kind].id
    starts = np.flatnonzero(mask & ~np.concatenate(([False], mask[:-1])))
    ends = np.flatnonzero(mask & ~np.concatenate((mask[1:], [False])))
    return list(zip(starts, ends))


def _points(rows):
    return ({(int(r["x0"]), int(r["y0"])) for r in rows} |
            {(int(r["x1"]), int(r["y1"])) for r in rows})


@pytest.fixture(scope="module")
def deinopis():
    return SPECIES["net-casting-spider"]()


@pytest.fixture(scope="module")
def ordgarius():
    return SPECIES["magnificent-spider"]()


@pytest.fixture(scope="module")
def latrodectus():
    return SPECIES["redback-spider"]()


def test_snare_rest_is_the_anchor_and_the_end_of_her_last_record(deinopis, ordgarius, latrodectus):
    for result in (deinopis, ordgarius, latrodectus):
        rest = result.rest[0]
        last = result.records[-1]
        assert (int(last["x1"]), int(last["y1"])) == (round(rest["x"]*4), round(rest["y"]*4))
        assert result.metadata["anchor"] == [rest["x"], rest["y"]]
        assert result.metadata["kind"] == "snare"


def test_deinopis_net_corners_are_her_leg_tips(deinopis):
    rows = deinopis.records
    rest = deinopis.rest[0]
    assert rest["pose"] == "net" and rest["angle"] == pytest.approx(math.pi/2)
    tips = rest_points_px("net-casting-spider", rest["x"], rest["y"], rest["angle"],
                          BY_ID["net-casting-spider"].mm_per_px)
    frame = _points(rows[rows["kind"] == BY_NAME["FRAME"].id])
    for leg in (0, 1, 4, 5):
        corner = min(frame, key=lambda p: math.dist(p, (tips[leg][0]*4, tips[leg][1]*4)))
        assert math.dist(corner, (tips[leg][0]*4, tips[leg][1]*4)) <= math.sqrt(2)/2  # ≤ 1/8 px


def test_deinopis_every_zig_is_two_strokes_1_2_px_apart(deinopis):
    rows = deinopis.records
    runs = _runs(rows, "CRIBELLATE")
    assert len(runs) >= 30  # one run per combed row
    for start, end in runs:
        strokes = rows[start:end+1]
        half = len(strokes)//2
        forward, back = strokes[:half], strokes[half:][::-1]
        # Interior zigs (the first and last stubs touch the frame).
        for a, b in zip(forward[1:-1], back[1:-1]):
            p0 = np.array([a["x0"], a["y0"]], float)/4
            p1 = np.array([a["x1"], a["y1"]], float)/4
            q = (np.array([b["x0"], b["y0"]], float) + np.array([b["x1"], b["y1"]], float))/8
            direction = (p1-p0)/np.linalg.norm(p1-p0)
            other = (np.array([b["x0"], b["y0"]], float)-np.array([b["x1"], b["y1"]], float))/4
            assert abs(float(np.dot(direction, other/np.linalg.norm(other)))) > 0.97  # parallel
            separation = abs(float(direction[0]*(q-p0)[1] - direction[1]*(q-p0)[0]))
            assert abs(separation-1.2) <= 0.36


def test_ordgarius_bolas_hangs_through_leg_two_and_ends_sticky(ordgarius):
    rows = ordgarius.records
    rest = ordgarius.rest[0]
    assert rest["pose"] == "hanging" and rest["angle"] == 0
    (start, end), = _runs(rows, "BOLAS")
    bolas = rows[start:end+1]
    assert np.all(bolas["flags"][:-1] & STICKY == 0) and bolas["flags"][-1] & STICKY
    assert (int(bolas[0]["x0"]), int(bolas[0]["y0"])) == (round(rest["x"]*4), round(rest["y"]*4))
    tip = rest_points_px("magnificent-spider", rest["x"], rest["y"], 0,
                         BY_ID["magnificent-spider"].mm_per_px)[1]
    assert (int(bolas[0]["x1"]), int(bolas[0]["y1"])) == (round(tip[0]*4), round(tip[1]*4))
    sacs = rows[rows["kind"] == BY_NAME["EGGSAC"].id]
    assert tuple(sacs[sacs["width"] >= 60][["r", "g", "b"]][0]) == (0x7a, 0x53, 0x34)
    # 2–3 sacs, each hung from the branch by one dry stalk.
    assert 2 <= int(np.sum(sacs["r"] == 0xcd)) <= 3
    assert len(rows) < 1000


def test_latrodectus_gumfoot_split_tangle_and_retreat(latrodectus):
    rows = latrodectus.records
    gumfoot = rows[rows["kind"] == BY_NAME["GUMFOOT"].id]
    upper, lower = gumfoot[0::2], gumfoot[1::2]
    assert 12 <= len(upper) == len(lower) <= 20
    assert np.all(upper["flags"] & STICKY == 0) and np.all(lower["flags"] & STICKY)
    for top, bottom in zip(upper, lower):
        assert (top["x1"], top["y1"]) == (bottom["x0"], bottom["y0"])
        whole = math.dist((top["x0"], top["y0"]), (bottom["x1"], bottom["y1"]))
        fraction = math.dist((top["x0"], top["y0"]), (top["x1"], top["y1"]))/whole
        assert abs(fraction-0.88) <= 1/whole  # whole is in quarter-pixels: ≤ ¼ px
        assert abs(int(bottom["x1"])-int(top["x0"])) < 0.25*whole  # nearly vertical
    tangle = rows[rows["kind"] == BY_NAME["TANGLE"].id]
    assert round(0.35*255) <= tangle["alpha"].min() < tangle["alpha"].max() <= round(0.6*255)
    points = _points(tangle)
    retreat = rows[rows["kind"] == BY_NAME["RETREAT"].id]
    assert 80 <= len(retreat) <= 140
    assert 60 <= len(points - _points(retreat) - _points(rows[(rows["flags"] & ENV) != 0])) <= 110
    lengths = np.hypot(tangle["x1"].astype(float)-tangle["x0"],
                       tangle["y1"].astype(float)-tangle["y0"])/4
    assert lengths.max() <= 160.5
