"""Anatomical data and the net/filament placement contract."""

import math

import pytest

from spun.spider import extent_px, glyph, rest_points_px

IDS = (
    "golden-orb-weaver", "st-andrews-cross", "garden-orb-weaver",
    "leaf-curling-spider", "christmas-jewel-spider", "scorpion-tailed-spider",
    "net-casting-spider", "magnificent-spider", "redback-spider",
)


@pytest.mark.parametrize("species_id", IDS)
def test_glyph_schema_and_gait(species_id):
    g = glyph(species_id)
    assert 1 <= g["scale"] <= 2
    assert g["strideMm"] > 0
    assert len(g["gait"]) == 8 and len(g["rest"]) == 8
    assert len(g["legs"]["width"]) == 3
    for frame in (*g["gait"], g["rest"]):
        assert len(frame) == 8
        assert all(len(leg) == 4 and all(len(joint) == 2 for joint in leg) for leg in frame)
    for shape in g["body"]:
        assert shape["type"] in ("ellipse", "polygon")
        assert all(shape[key] is None or shape[key].startswith("#") for key in ("fill", "stroke"))
        assert 0 <= shape["alpha"] <= 1
        if shape["type"] == "ellipse":
            assert shape["rx"] > 0 and shape["ry"] > 0
        else:
            assert len(shape["points"]) >= 3
    assert all(eye["r"] > eye["glint"]["r"] > 0 for eye in g["eyes"])
    # Continuity across frame 7 -> 0 is the same stride increment as
    # continuity across each of the other consecutive stance frames.
    stride_step = g["strideMm"] / 8
    for leg in range(8):
        dx = g["gait"][0][leg][3][0] - g["gait"][7][leg][3][0]
        assert abs(dx) <= stride_step * 4.1
        for a in (g["gait"][n][leg][3] for n in range(8)):
            assert all(math.isfinite(v) for v in a)
    for leg in range(8):
        stance_first = (leg % 4 + leg // 4) % 2 == 0
        for frame in (range(0, 3) if stance_first else range(4, 7)):
            x0 = g["gait"][frame][leg][3][0]
            x1 = g["gait"][frame + 1][leg][3][0]
            assert x1 - x0 == pytest.approx(-stride_step)


@pytest.mark.parametrize("species_id", IDS)
def test_rotated_rest_tips_and_extents(species_id):
    g = glyph(species_id)
    x, y, theta, mm_per_px = 421, 517, .73, .6
    points = rest_points_px(species_id, x, y, theta, mm_per_px)
    bounds = extent_px(species_id, x, y, theta, mm_per_px)
    assert len(points) == 8
    for tip, leg in zip(points, g["rest"]):
        px, py = leg[-1]
        f = g["scale"] / mm_per_px
        assert tip == pytest.approx((x + f*(math.cos(theta)*px-math.sin(theta)*py),
                                     y + f*(math.sin(theta)*px+math.cos(theta)*py)))
        assert bounds[0] <= tip[0] <= bounds[2] and bounds[1] <= tip[1] <= bounds[3]


def test_deinopis_net_held_at_convex_corners():
    g = glyph("net-casting-spider")
    quad = [g["rest"][i][-1] for i in (1, 0, 4, 5)]
    crosses = []
    for a, b, c in zip(quad, quad[1:]+quad[:1], quad[2:]+quad[:2]):
        crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    assert all(value > 0 for value in crosses)
    edges = [math.dist(a,b) for a,b in zip(quad,quad[1:]+quad[:1])]
    assert edges == pytest.approx((20,16,20,16),rel=.15)
    assert glyph("magnificent-spider")["rest"][1][-1] == [0,8]
    assert glyph("leaf-curling-spider")["restVisible"] == {
        "body": False, "eyes": False, "legFromJoint": 2}


def test_ordgarius_has_a_stout_near_body_leg_span():
    spider = glyph("magnificent-spider")
    body_length = 14
    y_positions = [joint[1] for leg in spider["rest"] for joint in leg]
    span = max(y_positions) - min(y_positions)
    assert 1.3*body_length <= span <= 1.6*body_length
    assert spider["legs"]["width"][0] >= body_length*.09
    abdomen = spider["body"][0]
    assert .9 <= abdomen["rx"]/abdomen["ry"] <= 1.1
