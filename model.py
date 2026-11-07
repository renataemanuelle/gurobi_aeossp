"""Build and solve the AEOSSP Integer Linear Program with Gurobi.

Formulation
-----------
Variables:  x_i ∈ {0,1}  for each acquisition i
Objective:  max Σ score_i · x_i

Constraints
  1. Request limit     — per ID group: Σ x_i ≤ max(stereo+1, strips)
  2. No temporal overlap — per satellite pair with overlapping windows
  3. Maneuver feasibility — per satellite pair without enough slew gap
  4. Stereo enforcement  — stereo acq requires ≥ 1 partner from another orbit
"""

import math
import time as _time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import gurobipy as gp
from gurobipy import GRB

from config import SLEW_RATE_DEG_PER_SEC, STEREO_ORBIT_THRESHOLD_SEC
from instance_parser import Acquisition


def _angle_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Central angle (degrees) between two satellite sub-points.

    Both positions share the same orbital altitude, so the angle equals
    the great-circle angular distance on a sphere of radius R+h.
    """
    la1 = math.radians(lat1)
    lo1 = math.radians(lon1)
    la2 = math.radians(lat2)
    lo2 = math.radians(lon2)

    cos_a = (math.cos(la1) * math.cos(la2) * math.cos(lo1 - lo2)
             + math.sin(la1) * math.sin(la2))
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def build_and_solve(
    acquisitions: List[Acquisition],
    time_limit: float,
    log_file: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Construct the AEOSSP ILP, solve it, and return solution metadata.

    Parameters
    ----------
    acquisitions : list[Acquisition]
        Parsed acquisition data (one per CSV row).
    time_limit : float
        Gurobi TimeLimit in seconds.
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

    # ---- Gurobi environment & model ----
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 1 if verbose else 0)
    if log_file:
        env.setParam("LogFile", log_file)
    env.start()

    model = gp.Model("AEOSSP", env=env)
    model.setParam("TimeLimit", time_limit)
    model.setParam("Threads", 0)          # auto-detect
    model.setParam("MIPFocus", 1)         # emphasise feasible solutions

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
    # ------------------------------------------------------------------
    sat_groups: Dict[str, List[int]] = defaultdict(list)
    for i, a in enumerate(acquisitions):
        sat_groups[a.satellite].append(i)

    max_maneuver = 180.0 / SLEW_RATE_DEG_PER_SEC  # 72 s upper bound

    n_conflict = 0
    for sat_id, indices in sat_groups.items():
        indices.sort(key=lambda i: acquisitions[i].time)

        for pa in range(len(indices)):
            i = indices[pa]
            ai = acquisitions[i]
            end_i = ai.time + math.ceil(ai.duration)

            for pb in range(pa + 1, len(indices)):
                j = indices[pb]
                aj = acquisitions[j]

                # Early exit: no more possible conflicts
                if aj.time >= end_i + max_maneuver:
                    break

                end_j = aj.time + math.ceil(aj.duration)

                # Overlap?
                if aj.time < end_i:
                    model.addConstr(x[i] + x[j] <= 1,
                                    name=f"ovlp_{i}_{j}")
                    n_conflict += 1
                    continue

                # Maneuver feasibility
                gap = aj.time - end_i
                angle = _angle_deg(ai.sat_lat, ai.sat_lon,
                                   aj.sat_lat, aj.sat_lon)
                if gap < angle / SLEW_RATE_DEG_PER_SEC:
                    model.addConstr(x[i] + x[j] <= 1,
                                    name=f"mnvr_{i}_{j}")
                    n_conflict += 1

    if verbose:
        print(f"    {n_conflict} conflict constraints (overlap + maneuver)")

    # ------------------------------------------------------------------
    # Constraint 4 — Stereo enforcement
    # ------------------------------------------------------------------
    n_stereo = 0
    for i, ai in enumerate(acquisitions):
        if ai.stereo <= 0:
            continue

        partners = [
            j for j in id_groups[ai.req_id]
            if j != i
            and acquisitions[j].satellite == ai.satellite
            and acquisitions[j].stereo > 0
            and abs(acquisitions[j].time - ai.time) > STEREO_ORBIT_THRESHOLD_SEC
        ]

        if not partners:
            x[i].UB = 0
        else:
            model.addConstr(
                x[i] <= gp.quicksum(x[j] for j in partners),
                name=f"stereo_{i}",
            )
        n_stereo += 1

    if verbose:
        print(f"    {n_stereo} stereo constraints")

    # ------------------------------------------------------------------
    model.update()
    build_time = _time.perf_counter() - t0

    if verbose:
        print(f"  Model ready: {model.NumVars} vars, "
              f"{model.NumConstrs} constraints  "
              f"(built in {build_time:.1f} s)")
        print(f"  Optimizing with TimeLimit = {time_limit} s …")

    model.optimize()

    # ---- Collect results ----
    gurobi_ver = ".".join(str(v) for v in gp.gurobi.version())
    result: Dict[str, Any] = {
        "num_acquisitions": n,
        "num_variables": model.NumVars,
        "num_constraints": model.NumConstrs,
        "num_request_constraints": n_req,
        "num_conflict_constraints": n_conflict,
        "num_stereo_constraints": n_stereo,
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
