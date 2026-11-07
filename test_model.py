"""Smoke test with a small synthetic instance.

Validates that the ILP formulation builds correctly and that all four
constraint types behave as expected.  Does NOT require real instance files
or a full Gurobi license (the free limited license handles this size).
"""

import math
import os
import sys
import tempfile

from instance_parser import Acquisition
from model import build_and_solve, _angle_deg


def _make_acq(row_pos, idx, req_id, stereo, satellite,
              lat, lon, t, strips, duration, score):
    return Acquisition(
        idx=idx, row_pos=row_pos, req_id=req_id, stereo=stereo,
        satellite=satellite, sat_lat=lat, sat_lon=lon,
        time=t, strips=strips, duration=duration, score=score,
    )


def test_basic_selection():
    """Two non-conflicting acquisitions — both should be selected."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1",  0.0,  0.0,  100, 1, 5, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT1",  0.0,  0.0, 1000, 1, 5, 20.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"], f"Expected OPTIMAL, got {sol['status_str']}"
    assert sol["num_selected"] == 2, f"Expected 2 selected, got {sol['num_selected']}"
    assert abs(sol["objective"] - 30.0) < 1e-6
    print("  PASS  basic_selection")


def test_overlap_constraint():
    """Two overlapping acquisitions on the same satellite — only one selected."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1", 0.0, 0.0, 100, 1, 10, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT1", 0.0, 0.0, 105, 1, 10, 20.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 1
    assert abs(sol["objective"] - 20.0) < 1e-6
    print("  PASS  overlap_constraint")


def test_overlap_different_satellites():
    """Overlapping in time but on different satellites — both selected."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1", 0.0, 0.0, 100, 1, 10, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT2", 0.0, 0.0, 105, 1, 10, 20.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 2
    assert abs(sol["objective"] - 30.0) < 1e-6
    print("  PASS  overlap_different_satellites")


def test_request_limit():
    """Three acquisitions for the same request (strips=1, stereo=0) → at most 1."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1",  0.0,   0.0, 100, 1, 5, 10.0),
        _make_acq(1, 1, "R1", 0, "SAT1",  0.0,   0.0, 500, 1, 5, 20.0),
        _make_acq(2, 2, "R1", 0, "SAT1",  0.0,   0.0, 900, 1, 5, 15.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 1
    assert abs(sol["objective"] - 20.0) < 1e-6
    print("  PASS  request_limit")


def test_request_limit_stereo():
    """Request with stereo=1 → limit = max(2, strips=1) = 2."""
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0, 0,  100,  1, 5, 10.0),
        _make_acq(1, 1, "R1", 1, "SAT1", 0, 0,  800,  1, 5, 20.0),
        _make_acq(2, 2, "R1", 1, "SAT1", 0, 0, 1600,  1, 5, 15.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 2
    assert abs(sol["objective"] - 35.0) < 1e-6
    print("  PASS  request_limit_stereo")


def test_maneuver_constraint():
    """Two acquisitions separated by small gap at wide angle — conflict."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1",   0.0,   0.0, 100, 1, 5, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT1",  40.0,  60.0, 108, 1, 5, 20.0),
    ]
    angle = _angle_deg(0, 0, 40, 60)
    gap = 108 - (100 + math.ceil(5))  # 108 - 105 = 3
    maneuver_time = angle / 2.5
    assert gap < maneuver_time, "Sanity: gap should be < maneuver time"

    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 1
    assert abs(sol["objective"] - 20.0) < 1e-6
    print("  PASS  maneuver_constraint")


def test_stereo_enforcement():
    """Stereo acq without a partner on a different orbit → forced to 0."""
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0, 0, 100, 1, 5, 100.0),
        _make_acq(1, 1, "R2", 0, "SAT1", 0, 0, 500, 1, 5,   5.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert 0 not in sol["selected_indices"], "Stereo acq 0 should be excluded"
    assert sol["num_selected"] == 1
    assert abs(sol["objective"] - 5.0) < 1e-6
    print("  PASS  stereo_enforcement_no_partner")


def test_stereo_with_partner():
    """Stereo acq with a viable partner (same ID, same sat, epoch diff > 600)."""
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0, 0,  100, 1, 5, 50.0),
        _make_acq(1, 1, "R1", 1, "SAT1", 0, 0, 1000, 1, 5, 50.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 2
    assert abs(sol["objective"] - 100.0) < 1e-6
    print("  PASS  stereo_with_partner")


def test_stereo_partner_too_close():
    """Two stereo acqs same ID/sat but epoch diff < 600 → no valid partner."""
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0, 0, 100, 1, 5, 50.0),
        _make_acq(1, 1, "R1", 1, "SAT1", 0, 0, 500, 1, 5, 50.0),
    ]
    sol = build_and_solve(acqs, time_limit=30, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 0
    assert abs(sol["objective"] - 0.0) < 1e-6
    print("  PASS  stereo_partner_too_close")


def test_angle_calculation():
    """Sanity check on the central-angle function."""
    assert abs(_angle_deg(0, 0, 0, 0)) < 1e-10
    assert abs(_angle_deg(0, 0, 0, 90) - 90.0) < 1e-6
    assert abs(_angle_deg(0, 0, 90, 0) - 90.0) < 1e-6
    assert abs(_angle_deg(0, 0, 0, 180) - 180.0) < 1e-6
    assert abs(_angle_deg(45, 0, -45, 0) - 90.0) < 1e-6
    print("  PASS  angle_calculation")


if __name__ == "__main__":
    tests = [
        test_angle_calculation,
        test_basic_selection,
        test_overlap_constraint,
        test_overlap_different_satellites,
        test_request_limit,
        test_request_limit_stereo,
        test_maneuver_constraint,
        test_stereo_enforcement,
        test_stereo_with_partner,
        test_stereo_partner_too_close,
    ]

    print(f"Running {len(tests)} tests …\n")
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
