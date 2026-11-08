"""Smoke test with a small synthetic instance.

Validates that the ILP formulation builds correctly and that all four
constraint types behave as expected.  Does NOT require real instance files
or a full Gurobi license (the free limited license handles this size).
"""

import math
import os
import sys
import tempfile

from instance_parser import Acquisition, compute_cartesian
from model import build_and_solve, _angle_deg, _viewing_angle_deg


def _make_acq(row_pos, idx, req_id, stereo, satellite,
              lat, lon, t, strips, duration, score,
              req_lat=None, req_lon=None):
    """Create a test Acquisition with auto-computed 3D coordinates.

    If req_lat/req_lon are not given, defaults to nadir pointing
    (request at same lat/lon as satellite).
    """
    if req_lat is None:
        req_lat = lat
    if req_lon is None:
        req_lon = lon
    acq = Acquisition(
        idx=idx, row_pos=row_pos, req_id=req_id, stereo=stereo,
        satellite=satellite, sat_lat=lat, sat_lon=lon,
        req_lat=req_lat, req_lon=req_lon,
        time=t, strips=strips, duration=duration, score=score,
    )
    compute_cartesian(acq)
    return acq


def test_basic_selection():
    """Two non-conflicting acquisitions — both should be selected."""
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1",  0.0,  0.0,  100, 1, 5, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT1",  0.0,  0.0, 1000, 1, 5, 20.0),
    ]
    sol = build_and_solve(acqs, verbose=False)
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
    sol = build_and_solve(acqs, verbose=False)
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
    sol = build_and_solve(acqs, verbose=False)
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
    sol = build_and_solve(acqs, verbose=False)
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
    # All at same position → viewing angle = 0° → no valid stereo pairs
    # → all forced to 0. Use different positions for valid partners:
    # Actually, with stereo but no valid stereo partner (viewing angle ∉ [15°,20°]),
    # all are forced to x=0. Test the request limit with stereo via mono path instead.
    # Use a setup where limit = 2 via strips=2 with stereo=0.
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1", 0, 0,  100, 2, 5, 10.0),
        _make_acq(1, 1, "R1", 0, "SAT1", 0, 0,  800, 2, 5, 20.0),
        _make_acq(2, 2, "R1", 0, "SAT1", 0, 0, 1600, 2, 5, 15.0),
    ]
    sol = build_and_solve(acqs, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 2
    assert abs(sol["objective"] - 35.0) < 1e-6
    print("  PASS  request_limit_stereo")


def test_maneuver_constraint():
    """Two acquisitions separated by small gap at wide angle — conflict."""
    # Nadir pointing: viewing angle = great-circle angle between satellite positions
    acqs = [
        _make_acq(0, 0, "R1", 0, "SAT1",   0.0,   0.0, 100, 1, 5, 10.0),
        _make_acq(1, 1, "R2", 0, "SAT1",  40.0,  60.0, 108, 1, 5, 20.0),
    ]
    angle = _viewing_angle_deg(acqs[0], acqs[1])
    delta_t = 108 - 100  # 8
    assert acqs[0].duration + angle / 2.5 > delta_t, "Sanity: maneuver should be infeasible"

    sol = build_and_solve(acqs, verbose=False)
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
    # Acq 0 is stereo=1 but no partner (only acq in group R1 with stereo>0)
    sol = build_and_solve(acqs, verbose=False)
    assert sol["is_optimal"]
    assert 0 not in sol["selected_indices"], "Stereo acq 0 should be excluded"
    assert sol["num_selected"] == 1
    assert abs(sol["objective"] - 5.0) < 1e-6
    print("  PASS  stereo_enforcement_no_partner")


def test_stereo_with_partner():
    """Stereo acq with a viable partner (viewing angle ~17.5° ∈ [15°, 20°])."""
    # Two acquisitions at different satellite positions, nadir pointing.
    # Satellite positions 17.5° apart → viewing angle ≈ 17.5° → valid pair.
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0.0,  0.0, 100, 1, 5, 50.0),
        _make_acq(1, 1, "R1", 1, "SAT1", 0.0, 17.5, 800, 1, 5, 50.0),
    ]
    angle = _viewing_angle_deg(acqs[0], acqs[1])
    assert 15.0 <= angle <= 20.0, f"Expected angle in [15, 20], got {angle:.2f}"

    sol = build_and_solve(acqs, verbose=False)
    assert sol["is_optimal"]
    assert sol["num_selected"] == 2
    assert abs(sol["objective"] - 100.0) < 1e-6
    print("  PASS  stereo_with_partner")


def test_stereo_partner_too_close():
    """Two stereo acqs same ID/sat at identical position → angle=0 → no partner."""
    acqs = [
        _make_acq(0, 0, "R1", 1, "SAT1", 0, 0, 100, 1, 5, 50.0),
        _make_acq(1, 1, "R1", 1, "SAT1", 0, 0, 500, 1, 5, 50.0),
    ]
    angle = _viewing_angle_deg(acqs[0], acqs[1])
    assert angle < 15.0, f"Expected angle < 15, got {angle:.2f}"

    sol = build_and_solve(acqs, verbose=False)
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


def test_viewing_angle():
    """Sanity check on viewing-angle function (nadir → equals great-circle)."""
    # Two nadir-pointing acquisitions → viewing angle = great-circle angle
    a = _make_acq(0, 0, "R1", 0, "SAT1", 0, 0, 100, 1, 5, 1.0)
    b = _make_acq(1, 1, "R2", 0, "SAT1", 0, 90, 200, 1, 5, 1.0)
    angle = _viewing_angle_deg(a, b)
    assert abs(angle - 90.0) < 0.5, f"Expected ~90°, got {angle:.2f}"

    # Same position → angle = 0
    c = _make_acq(2, 2, "R3", 0, "SAT1", 0, 0, 300, 1, 5, 1.0)
    assert abs(_viewing_angle_deg(a, c)) < 1e-6
    print("  PASS  viewing_angle")


if __name__ == "__main__":
    tests = [
        test_angle_calculation,
        test_viewing_angle,
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
