"""Build and solve the AEOSSP Integer Linear Program with Gurobi.

Formulation
-----------
Variables:  x_i ∈ {0,1}  for each acquisition i
Objective:  max Σ score_i · x_i

Constraints
  1. Request limit     — per ID group: Σ x_i ≤ max(stereo+1, strips)
  2. No temporal overlap — per satellite pair with overlapping intervals
  3. Maneuver feasibility — per satellite pair without enough slew time
     (lifted constraint for non-adjacent pairs)
  4. Stereo enforcement  — stereo acq requires ≥ 1 partner with viewing
     angle in [15°, 20°] (matching RKO stereo pair criterion)
"""

import math
import time as _time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import gurobipy as gp
from gurobipy import GRB

from config import SLEW_RATE_DEG_PER_SEC, STEREO_ANGLE_MIN, STEREO_ANGLE_MAX
from instance_parser import Acquisition


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def _angle_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Central angle (degrees) between two points on a sphere."""
    la1 = math.radians(lat1)
    lo1 = math.radians(lon1)
    la2 = math.radians(lat2)
    lo2 = math.radians(lon2)

    cos_a = (math.cos(la1) * math.cos(la2) * math.cos(lo1 - lo2)
             + math.sin(la1) * math.sin(la2))
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def _viewing_angle_deg(a: Acquisition, b: Acquisition) -> float:
    """Angle (degrees) between two line-of-sight vectors (sat → request).

    This matches the RKO ``maneuver_angle_deg_fast`` function exactly.
    """
    v1x = a.sat_x - a.req_x
    v1y = a.sat_y - a.req_y
    v1z = a.sat_z - a.req_z

    v2x = b.sat_x - b.req_x
    v2y = b.sat_y - b.req_y
    v2z = b.sat_z - b.req_z

    dot = v1x * v2x + v1y * v2y + v1z * v2z
    n1 = math.sqrt(v1x * v1x + v1y * v1y + v1z * v1z)
    n2 = math.sqrt(v2x * v2x + v2y * v2y + v2z * v2z)

    if n1 == 0.0 or n2 == 0.0:
        return 0.0

    cos_theta = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.degrees(math.acos(cos_theta))


# ---------------------------------------------------------------------------
# Pre-compute stereo pairs (same criterion as RKO: viewing angle ∈ [15°, 20°])
# ---------------------------------------------------------------------------

def _compute_stereo_pairs(
    acquisitions: List[Acquisition],
) -> Tuple[List[Tuple[int, int]], Dict[int, List[int]]]:
    """Return (stereo_pairs, stereo_partners) matching the RKO criterion."""
    stereo_groups: Dict[str, List[int]] = defaultdict(list)
    for i, a in enumerate(acquisitions):
        if a.stereo > 0:
            stereo_groups[a.req_id].append(i)

    stereo_pairs: List[Tuple[int, int]] = []
    stereo_partners: Dict[int, List[int]] = defaultdict(list)

    for _req_id, s_indices in stereo_groups.items():
        for pa in range(len(s_indices)):
            for pb in range(pa + 1, len(s_indices)):
                i, j = s_indices[pa], s_indices[pb]
                angle = _viewing_angle_deg(acquisitions[i], acquisitions[j])
                if STEREO_ANGLE_MIN <= angle <= STEREO_ANGLE_MAX:
                    stereo_pairs.append((i, j))
                    stereo_partners[i].append(j)
                    stereo_partners[j].append(i)

    return stereo_pairs, stereo_partners


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def build_and_solve(
    acquisitions: List[Acquisition],
    log_file: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Construct the AEOSSP ILP, solve it, and return solution metadata.

    The solver runs as an exact method with no time limit, optimizing
    until proven optimality (or infeasibility).

    Parameters
    ----------
    acquisitions : list[Acquisition]
        Parsed acquisition data (one per CSV row, after dedup).
    log_file : str | None
        If given, Gurobi writes its log here.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    dict  with keys: status_str, objective, gap, is_optimal, runtime, …
    """
    n = len(acquisitions)
    t0 = _time.perf_counter()

    if verbose:
        print(f"  Building model with {n} acquisitions …")

    # ---- Pre-compute stereo pairs ----
    stereo_pairs, stereo_partners = _compute_stereo_pairs(acquisitions)

    if verbose:
        print(f"    {len(stereo_pairs)} stereo pairs (viewing angle "
              f"[{STEREO_ANGLE_MIN}°, {STEREO_ANGLE_MAX}°])")

    # ---- Gurobi environment & model ----
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 1 if verbose else 0)
    if log_file:
        env.setParam("LogFile", log_file)
    env.start()

    model = gp.Model("AEOSSP", env=env)
    model.setParam("Threads", 0)          # auto-detect

    # ---- Decision variables ----
    x = model.addVars(n, vtype=GRB.BINARY, name="x")

    # ---- Objective ----
    model.setObjective(
        gp.quicksum(acquisitions[i].score * x[i] for i in range(n)),
        GRB.MAXIMIZE,
    )

    # ------------------------------------------------------------------
    # Constraint 1 — Request limit per ID group
    # ------------------------------------------------------------------
    id_groups: Dict[str, List[int]] = defaultdict(list)
    for i, a in enumerate(acquisitions):
        id_groups[a.req_id].append(i)

    n_req = 0
    for req_id, indices in id_groups.items():
        grp_stereo = max(acquisitions[i].stereo for i in indices)
        grp_strips = max(acquisitions[i].strips for i in indices)
        limit = max(grp_stereo + 1, grp_strips)

        if limit < len(indices):
            model.addConstr(
                gp.quicksum(x[i] for i in indices) <= limit,
                name=f"req_{req_id}",
            )
            n_req += 1

    if verbose:
        print(f"    {n_req} request-limit constraints")

    # ------------------------------------------------------------------
    # Constraints 2 & 3 — Overlap + maneuver (per satellite)
    #
    # Overlap:  pairwise x_i + x_j ≤ 1  (always correct)
    # Maneuver: lifted constraint for non-adjacent pairs:
    #     x_i + x_j  - Σ_{k between i,j on same sat} x_k  ≤ 1
    #
    # The lifted form allows both i and j to be selected when an
    # intermediate acquisition k is also selected (making them
    # non-adjacent), which matches the RKO greedy decoder behaviour.
    # ------------------------------------------------------------------
    sat_groups: Dict[str, List[int]] = defaultdict(list)
    for i, a in enumerate(acquisitions):
        sat_groups[a.satellite].append(i)

    max_maneuver = 180.0 / SLEW_RATE_DEG_PER_SEC  # 72 s upper bound

    n_overlap = 0
    n_maneuver = 0
    for sat_id, indices in sat_groups.items():
        indices.sort(key=lambda i: acquisitions[i].time)

        for pa in range(len(indices)):
            i = indices[pa]
            ai = acquisitions[i]

            for pb in range(pa + 1, len(indices)):
                j = indices[pb]
                aj = acquisitions[j]

                delta_t = aj.time - ai.time

                # Early exit: beyond maximum infeasible delta_t
                if delta_t >= ai.duration + max_maneuver:
                    break

                # Overlap: j starts before i's interval ends (ceil'd duration)
                if aj.time < ai.time + math.ceil(ai.duration):
                    model.addConstr(x[i] + x[j] <= 1,
                                    name=f"ovlp_{i}_{j}")
                    n_overlap += 1
                    continue

                # Maneuver feasibility (matches RKO exactly):
                #   feasible iff duration_i + angle/speed ≤ delta_t
                angle = _viewing_angle_deg(ai, aj)
                t_maneuver = angle / SLEW_RATE_DEG_PER_SEC

                if ai.duration + t_maneuver > delta_t:
                    # Infeasible direct maneuver — use lifted constraint
                    between = [indices[pk] for pk in range(pa + 1, pb)]
                    if between:
                        model.addConstr(
                            x[i] + x[j]
                            - gp.quicksum(x[k] for k in between)
                            <= 1,
                            name=f"mnvr_{i}_{j}",
                        )
                    else:
                        model.addConstr(x[i] + x[j] <= 1,
                                        name=f"mnvr_{i}_{j}")
                    n_maneuver += 1

    if verbose:
        print(f"    {n_overlap} overlap constraints")
        print(f"    {n_maneuver} maneuver constraints (lifted)")

    # ------------------------------------------------------------------
    # Constraint 4 — Stereo enforcement
    # A stereo acquisition (stereo > 0) that has valid partners can
    # only be selected if at least one partner is also selected.
    # If NO valid partners exist (no pair with viewing angle ∈ [15°,20°]),
    # the acquisition is treated as mono (no constraint added),
    # matching the RKO greedy decoder behaviour.
    # ------------------------------------------------------------------
    n_stereo = 0
    n_stereo_free = 0
    for i, ai in enumerate(acquisitions):
        if ai.stereo <= 0:
            continue

        partners = stereo_partners.get(i, [])

        if not partners:
            n_stereo_free += 1
        else:
            model.addConstr(
                x[i] <= gp.quicksum(x[j] for j in partners),
                name=f"stereo_{i}",
            )
            n_stereo += 1

    if verbose:
        print(f"    {n_stereo} stereo constraints "
              f"({n_stereo_free} stereo acqs without partners → treated as mono)")

    # ------------------------------------------------------------------
    model.update()
    build_time = _time.perf_counter() - t0

    if verbose:
        print(f"  Model ready: {model.NumVars} vars, "
              f"{model.NumConstrs} constraints  "
              f"(built in {build_time:.1f} s)")
        print(f"  Optimizing (exact — no time limit) …")

    model.optimize()

    # ---- Collect results ----
    gurobi_ver = ".".join(str(v) for v in gp.gurobi.version())
    result: Dict[str, Any] = {
        "num_acquisitions": n,
        "num_variables": model.NumVars,
        "num_constraints": model.NumConstrs,
        "num_request_constraints": n_req,
        "num_overlap_constraints": n_overlap,
        "num_maneuver_constraints": n_maneuver,
        "num_stereo_constraints": n_stereo,
        "stereo_pairs": stereo_pairs,
        "build_time": build_time,
        "status": model.Status,
        "status_str": _status_str(model.Status),
        "runtime": model.Runtime,
        "node_count": int(model.NodeCount),
        "gurobi_version": gurobi_ver,
    }

    if model.SolCount > 0:
        result["objective"] = model.ObjVal
        result["best_bound"] = model.ObjBound
        result["gap"] = model.MIPGap
        selected = [i for i in range(n) if x[i].X > 0.5]
        result["num_selected"] = len(selected)
        result["selected_indices"] = [acquisitions[i].idx for i in selected]
        result["is_optimal"] = model.Status == GRB.OPTIMAL
    else:
        result["objective"] = None
        result["best_bound"] = None
        result["gap"] = None
        result["num_selected"] = 0
        result["selected_indices"] = []
        result["is_optimal"] = False

    model.dispose()
    env.dispose()
    return result


_STATUS_MAP = {
    GRB.OPTIMAL: "OPTIMAL",
    GRB.INFEASIBLE: "INFEASIBLE",
    GRB.INF_OR_UNBD: "INF_OR_UNBD",
    GRB.UNBOUNDED: "UNBOUNDED",
    GRB.CUTOFF: "CUTOFF",
    GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
    GRB.NODE_LIMIT: "NODE_LIMIT",
    GRB.TIME_LIMIT: "TIME_LIMIT",
    GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
    GRB.INTERRUPTED: "INTERRUPTED",
    GRB.NUMERIC: "NUMERIC",
    GRB.SUBOPTIMAL: "SUBOPTIMAL",
}


def _status_str(code: int) -> str:
    return _STATUS_MAP.get(code, f"UNKNOWN_{code}")
