"""Round-trip and hand-built counterexamples to each phase-one rule."""

import math

import numpy as np
import pytest

from spun.kinds import BY_NAME, ENV, GLUE, INVISIBLE, KINDS, STICKY
from spun.silkfile import (BEAD_DTYPE, COORD_SCALE, HEADER, NEVER, RECORD_DTYPE,
                           WIDTH_SCALE, quantize_coord, quantize_radius,
                           quantize_t, quantize_width, read_silk, write_silk)
from spun.validate import ValidationError, validate


def segment(a, b, kind="FRAME", flags=0, death=NEVER):
    return (*[quantize_coord(v) for p in (a, b) for v in p], death,
            BY_NAME[kind].id, quantize_width(BY_NAME[kind].width or 0),
            205, 214, 228, 255, flags, 230)


def metadata(records, rest, *, kind="snare"):
    stages = []
    for i, record in enumerate(records):
        label = KINDS[int(record["kind"])].label
        if label is not None and (not stages or stages[-1]["label"] != label):
            stages.append({"label": label, "start": i})
    stages.append({"label": "at rest", "start": len(records)})
    return {"kind": kind, "golden": False, "orbs": [],
            "timeline": np.linspace(0, len(records), 512).tolist(),
            "stages": stages, "rests": {0: rest}, "catalogueBytes": 10000,
            "indexBytes": 1000, "defaultBytes": 10000}


def tiny_snare():
    records = np.array([
        segment((0, 10), (10, 10), "SCAFFOLD", ENV),
        segment((10, 10), (20, 10), flags=STICKY),
        segment((20, 10), (10, 10), "WALK", INVISIBLE),
    ], dtype=RECORD_DTYPE)
    beads = np.array([(1, quantize_t(0.4), quantize_radius(1.25), GLUE)],
                     dtype=BEAD_DTYPE)
    return records, beads, metadata(records, (10, 10))


def tiny_orb():
    center = (50., 42.)
    directions = (0., 1.13, 2.45, 3.95, 5.18)
    points = [(center[0] + 20 * math.cos(theta), center[1] + 20 * math.sin(theta))
              for theta in directions]
    def on_ray(j, d):
        return (center[0] + d * math.cos(directions[j]),
                center[1] + d * math.sin(directions[j]))
    silk = [segment((50, 32), center, "SCAFFOLD", ENV)]
    for j in range(5):
        for d0, d1 in ((0, 7), (7, 12), (12, 18), (18, 20)):
            silk.append(segment(on_ray(j, d0), on_ray(j, d1), "RADIUS"))
        for d0, d1 in ((20, 18), (18, 12), (12, 7), (7, 0)):
            silk.append(segment(on_ray(j, d0), on_ray(j, d1), "WALK", INVISIBLE))
    for d0, d1 in ((0, 7), (7, 12), (12, 18)):
        silk.append(segment(on_ray(0, d0), on_ray(0, d1), "WALK", INVISIBLE))
    for row in (18, 12, 7):
        for j in range(5):
            silk.append(segment(on_ray(j, row), on_ray((j + 1) % 5, row), "CAPTURE", STICKY))
        if row != 7:
            next_row = 12 if row == 18 else 7
            silk.append(segment(on_ray(0, row), on_ray(0, next_row), "WALK", INVISIBLE))
    rows = np.array(silk, dtype=RECORD_DTYPE)
    info = metadata(rows, on_ray(0, 7), kind="orb")
    info["orbs"] = [{"builder": 0, "hub": center, "frame": points,
                     "radii": points, "openSectors": []}]
    return rows, np.zeros(0, dtype=BEAD_DTYPE), info


def validate_fixture(fixture):
    records, beads, info = fixture
    return validate(write_silk(100, 100, 1, records, beads), info)


def test_binary_round_trip_and_quantization():
    samples = [0.13, 1.125, 12.375, 95.987]
    for value in samples:
        assert abs(quantize_coord(value) / COORD_SCALE - value) <= 0.125
    for value in (0.531, 0.8125, 1.257, 7.968):
        assert abs(quantize_width(value) / WIDTH_SCALE - value) <= 1 / 64
    records, beads, _ = tiny_snare()
    data = write_silk(100, 100, 1, records, beads)
    assert len(data) == 32 + 20 * len(records) + 8 * len(beads)
    assert HEADER.unpack_from(data)[:5] == (b"SILK", 1, 32, 20, 8)
    assert data[32:32 + 20 * len(records)] == records.tobytes()
    assert data[32 + 20 * len(records):] == beads.tobytes()
    unpacked = read_silk(data)
    assert unpacked.records.dtype == RECORD_DTYPE
    assert unpacked.beads.dtype == BEAD_DTYPE
    np.testing.assert_array_equal(unpacked.records, records)
    np.testing.assert_array_equal(unpacked.beads, beads)
    assert write_silk(unpacked.width, unpacked.height, unpacked.builder_count,
                      unpacked.records, unpacked.beads) == data


def test_tiny_hand_built_snare_passes():
    assert len(validate_fixture(tiny_snare()).records) == 3


def test_tiny_hand_built_orb_passes():
    assert len(validate_fixture(tiny_orb()).records) > 50


@pytest.mark.parametrize("damage", [
    lambda raw: raw[:4] + b"X" + raw[5:],
    lambda raw: raw[:-1],
    lambda raw: raw + b"\x00",
    lambda raw: raw[:29] + b"\x01" + raw[30:],
])
def test_rule_1_rejects_bad_structure(damage):
    rows, beads, info = tiny_snare()
    raw = damage(write_silk(100, 100, 1, rows, beads))
    with pytest.raises(ValidationError, match="Rule 1:"):
        validate(raw, info)


def test_rule_1_rejects_zero_length_and_out_of_canvas():
    rows, beads, info = tiny_snare()
    rows[0]["x1"] = rows[0]["x0"]
    rows[0]["y1"] = rows[0]["y0"]
    with pytest.raises(ValidationError, match="Rule 1:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_snare()
    rows[1]["x1"] = 401
    with pytest.raises(ValidationError, match="Rule 1:"):
        validate_fixture((rows, beads, info))


def test_rule_2_rejects_teleport():
    rows, beads, info = tiny_snare()
    rows[2]["x0"] = quantize_coord(19)
    with pytest.raises(ValidationError, match="Rule 2:"):
        validate_fixture((rows, beads, info))


def test_rule_2_rejects_interleaved_builders():
    rows, beads, info = tiny_snare()
    rows = np.concatenate([rows, np.array([segment((10, 10), (10, 20),
                                                  "FRAME", flags=1 << 4),
                                          segment((10, 10), (20, 10))], dtype=RECORD_DTYPE)])
    info["timeline"] = np.linspace(0, len(rows), 512).tolist()
    info["stages"][-1]["start"] = len(rows)
    with pytest.raises(ValidationError, match="Rule 2:"):
        validate(write_silk(100, 100, 2, rows, beads), info)


def test_rule_3_rejects_walk_on_unspun_path():
    rows, beads, info = tiny_snare()
    rows[2]["y1"] = quantize_coord(11)
    with pytest.raises(ValidationError, match="Rule 3:"):
        validate_fixture((rows, beads, info))


def test_rule_4_rejects_invalid_death_and_wrong_aux_policy():
    rows, beads, info = tiny_snare()
    rows[2]["death"] = 2
    with pytest.raises(ValidationError, match="Rule 4:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_orb()
    rows[1]["kind"] = BY_NAME["AUX"].id
    with pytest.raises(ValidationError, match="Rule 4:"):
        validate_fixture((rows, beads, info))


def test_rule_5_rejects_hub_outside_frame():
    rows, beads, info = tiny_orb()
    info["orbs"][0]["frame"] = [[2, 2], [5, 2], [5, 5], [2, 5]]
    with pytest.raises(ValidationError, match="Rule 5:"):
        validate_fixture((rows, beads, info))


def test_rule_5_rejects_crossing_capture_chord():
    rows, beads, info = tiny_orb()
    captures = np.flatnonzero(rows["kind"] == BY_NAME["CAPTURE"].id)
    rows[captures[0]]["x1"] = rows[captures[2]]["x1"]
    rows[captures[0]]["y1"] = rows[captures[2]]["y1"]
    rows[captures[1]]["x0"] = rows[captures[0]]["x1"]
    rows[captures[1]]["y0"] = rows[captures[0]]["y1"]
    with pytest.raises(ValidationError, match="Rule 5:"):
        validate_fixture((rows, beads, info))

def test_rule_5_rejects_capture_in_open_sector():
    rows, beads, info = tiny_orb()
    info["orbs"][0]["openSectors"] = [[0.1, 1.0]]
    with pytest.raises(ValidationError, match="Rule 5:.*open sector"):
        validate_fixture((rows, beads, info))


def test_rule_6_rejects_uniform_spirograph_gaps():
    rows, beads, info = tiny_orb()
    angle = [math.tau * i / 5 for i in range(5)]
    info["orbs"][0]["radii"] = [[50 + 20 * math.cos(a), 42 + 20 * math.sin(a)]
                                   for a in angle]
    with pytest.raises(ValidationError, match="Rule 6:"):
        validate_fixture((rows, beads, info))

def test_rule_6_rejects_golden_web_without_turnbacks_or_high_hub():
    rows, beads, info = tiny_orb()
    info["golden"] = True
    with pytest.raises(ValidationError, match="Rule 6:.*golden"):
        validate_fixture((rows, beads, info))


def test_rule_7_rejects_bead_on_nonsticky_or_environment_host():
    rows, beads, info = tiny_snare()
    beads[0]["host"] = 0
    with pytest.raises(ValidationError, match="Rule 7:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_snare()
    rows[1]["flags"] = 0
    with pytest.raises(ValidationError, match="Rule 7:"):
        validate_fixture((rows, beads, info))

def test_rule_7_rejects_unsorted_beads():
    rows, beads, info = tiny_snare()
    beads = np.array([(1, 500, 12, 0), (1, 400, 12, 0)], dtype=BEAD_DTYPE)
    with pytest.raises(ValidationError, match="Rule 7:"):
        validate_fixture((rows, beads, info))


def test_rule_8_rejects_bad_timeline_and_rest():
    rows, beads, info = tiny_snare()
    info["timeline"] = [0, 3]
    with pytest.raises(ValidationError, match="Rule 8:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_snare()
    info["rests"][0] = (20, 10)
    with pytest.raises(ValidationError, match="Rule 8:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_snare()
    info["stages"].pop(1)
    with pytest.raises(ValidationError, match="Rule 8:"):
        validate_fixture((rows, beads, info))


def test_rule_9_rejects_catalogue_and_default_budget():
    rows, beads, info = tiny_snare()
    info["catalogueBytes"] = 3 * 1024 * 1024 + 1
    with pytest.raises(ValidationError, match="Rule 9:"):
        validate_fixture((rows, beads, info))
    rows, beads, info = tiny_snare()
    info["indexBytes"] = 400 * 1024
    with pytest.raises(ValidationError, match="Rule 9:"):
        validate_fixture((rows, beads, info))
