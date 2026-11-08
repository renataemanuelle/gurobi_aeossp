"""Solve a single AEOSSP instance with Gurobi and write results."""

import argparse
import csv
import os
from typing import Optional

from config import (
    DEFAULT_INSTANCES_DIR,
    DEFAULT_LOG_DIR,
    DEFAULT_RESULTS_DIR,
    INSTANCES,
)
from instance_parser import parse_instance
from model import build_and_solve


def solve_instance(
    tag: str,
    instances_dir: str = DEFAULT_INSTANCES_DIR,
    results_dir: str = DEFAULT_RESULTS_DIR,
    log_dir: Optional[str] = DEFAULT_LOG_DIR,
) -> dict:
    """Parse, solve and persist results for one instance.

    Returns the solution dictionary produced by :func:`model.build_and_solve`.
    """
    if tag not in INSTANCES:
        raise ValueError(f"Unknown instance tag: {tag}")

    cfg = INSTANCES[tag]

    print(f"\n{'=' * 64}")
    print(f"  Instance : {tag}   |A| = {cfg['size']}   (exact — no time limit)")
    print(f"{'=' * 64}")

    acquisitions, df_raw = parse_instance(tag, instances_dir)
    print(f"  Loaded {len(acquisitions)} acquisitions from CSV "
          f"({len(df_raw)} raw rows, {len(df_raw) - len(acquisitions)} duplicates removed)")

    log_file = None
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"gurobi_{tag}.log")

    solution = build_and_solve(acquisitions, log_file)

    os.makedirs(results_dir, exist_ok=True)
    _write_evaluation_csv(tag, acquisitions, df_raw, solution, results_dir)
    _write_solution_file(tag, solution, results_dir)

    print(f"\n  Status   : {solution['status_str']}")
    if solution["objective"] is not None:
        print(f"  Objective: {solution['objective']:.6f}")
        print(f"  Bound    : {solution['best_bound']:.6f}")
        print(f"  Gap      : {solution['gap'] * 100:.2f} %")
        print(f"  Selected : {solution['num_selected']} acquisitions")
    print(f"  Runtime  : {solution['runtime']:.1f} s")

    return solution


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_evaluation_csv(
    tag: str,
    acquisitions: list,
    df_raw,
    sol: dict,
    results_dir: str,
) -> None:
    """Write Evaluation_Gurobi_<tag>.csv matching the RKO evaluation format."""
    path = os.path.join(results_dir, f"Evaluation_Gurobi_{tag}.csv")

    n_dedup = len(acquisitions)
    n_raw = len(df_raw)
    unique_ids_dedup = len(set(a.req_id for a in acquisitions))
    unique_ids_raw = df_raw["ID"].nunique()

    stereo_pairs = sol.get("stereo_pairs", [])

    # Scenario stats (dedup'd)
    avg_angle = sum(a.angle for a in acquisitions) / n_dedup if n_dedup else 0
    avg_area = sum(a.area for a in acquisitions) / n_dedup if n_dedup else 0
    avg_price = sum(a.price for a in acquisitions) / n_dedup if n_dedup else 0
    avg_sun = sum(a.sun_elevation for a in acquisitions) / n_dedup if n_dedup else 0
    avg_cloud = sum(a.cloud_cover_estimate for a in acquisitions) / n_dedup if n_dedup else 0
    avg_prio = sum(a.priority for a in acquisitions) / n_dedup if n_dedup else 0

    # Scenario_raw stats (from raw DataFrame)
    df_raw.columns = df_raw.columns.str.strip()
    avg_angle_raw = df_raw["angle"].mean() if n_raw else 0
    avg_area_raw = df_raw["area"].mean() if n_raw else 0
    avg_price_raw = df_raw["price"].mean() if n_raw else 0
    avg_sun_raw = df_raw["sun elevation"].mean() if n_raw else 0
    avg_cloud_raw = df_raw["cloud cover estimate"].mean() if n_raw else 0
    avg_prio_raw = df_raw["priority"].mean() if n_raw else 0

    rows = [
        ("scenario", "requests", unique_ids_dedup),
        ("scenario", "attempts", n_dedup),
        ("scenario", "stereo_pairs", len(stereo_pairs)),
        ("scenario", "avg_angle", f"{avg_angle:.6f}"),
        ("scenario", "avg_area", f"{avg_area:.6f}"),
        ("scenario", "avg_price", f"{avg_price:.6f}"),
        ("scenario", "avg_sun_elevation", f"{avg_sun:.6f}"),
        ("scenario", "avg_cloud_cover", f"{avg_cloud:.6f}"),
        ("scenario", "avg_priority", f"{avg_prio:.6f}"),
        ("scenario_raw", "requests", unique_ids_raw),
        ("scenario_raw", "attempts", n_raw),
        ("scenario_raw", "avg_angle", f"{avg_angle_raw:.6f}"),
        ("scenario_raw", "avg_area", f"{avg_area_raw:.6f}"),
        ("scenario_raw", "avg_price", f"{avg_price_raw:.6f}"),
        ("scenario_raw", "avg_sun_elevation", f"{avg_sun_raw:.6f}"),
        ("scenario_raw", "avg_cloud_cover", f"{avg_cloud_raw:.6f}"),
        ("scenario_raw", "avg_priority", f"{avg_prio_raw:.6f}"),
    ]

    # Solution stats
    selected_idx_set = set(sol.get("selected_indices", []))
    selected_acqs = [a for a in acquisitions if a.idx in selected_idx_set]
    n_sel = len(selected_acqs)

    if n_sel > 0:
        unique_served = len(set(a.req_id for a in selected_acqs))
        total_score = sum(a.score for a in selected_acqs)
        total_profit = sum(a.price for a in selected_acqs)
        total_area = sum(a.area for a in selected_acqs)
        s_avg_cloud = sum(a.cloud_cover_estimate for a in selected_acqs) / n_sel
        cloud_lt10 = sum(1 for a in selected_acqs if a.cloud_cover_estimate < 10)
        cloud_gt30 = sum(1 for a in selected_acqs if a.cloud_cover_estimate > 30)
        s_avg_angle = sum(a.angle for a in selected_acqs) / n_sel
        angle_le10 = sum(1 for a in selected_acqs if a.angle <= 10)
        angle_ge30 = sum(1 for a in selected_acqs if a.angle >= 30)
        s_avg_prio = sum(a.priority for a in selected_acqs) / n_sel
        prio_counts = {k: 0 for k in range(1, 5)}
        for a in selected_acqs:
            if a.priority in prio_counts:
                prio_counts[a.priority] += 1
        s_avg_sun = sum(a.sun_elevation for a in selected_acqs) / n_sel
    else:
        unique_served = 0
        total_score = 0.0
        total_profit = 0.0
        total_area = 0.0
        s_avg_cloud = 0.0
        cloud_lt10 = 0
        cloud_gt30 = 0
        s_avg_angle = 0.0
        angle_le10 = 0
        angle_ge30 = 0
        s_avg_prio = 0.0
        prio_counts = {k: 0 for k in range(1, 5)}
        s_avg_sun = 0.0

    rows += [
        ("solution", "acquisitions", n_sel),
        ("solution", "unique_requests_served", unique_served),
        ("solution", "total_score", f"{total_score:.6f}"),
        ("solution", "ofv", f"{-total_score:.6f}"),
        ("solution", "total_profit", f"{total_profit:.6f}"),
        ("solution", "total_area", f"{total_area:.6f}"),
        ("solution", "avg_cloud_cover", f"{s_avg_cloud:.6f}"),
        ("solution", "cloud_good_lt10", cloud_lt10),
        ("solution", "cloud_bad_gt30", cloud_gt30),
        ("solution", "avg_angle", f"{s_avg_angle:.6f}"),
        ("solution", "angle_good_le10", angle_le10),
        ("solution", "angle_bad_ge30", angle_ge30),
        ("solution", "avg_priority", f"{s_avg_prio:.6f}"),
        ("solution", "priority_1", prio_counts[1]),
        ("solution", "priority_2", prio_counts[2]),
        ("solution", "priority_3", prio_counts[3]),
        ("solution", "priority_4", prio_counts[4]),
        ("solution", "avg_sun_elevation", f"{s_avg_sun:.6f}"),
    ]

    # Gurobi section
    stereo_complete = 0
    stereo_acq_selected = 0
    strip_acq_selected = 0
    for a in selected_acqs:
        if a.stereo > 0:
            stereo_acq_selected += 1
        if a.strips >= 2:
            strip_acq_selected += 1
    for i, j in stereo_pairs:
        if i in selected_idx_set and j in selected_idx_set:
            stereo_complete += 1

    total_time = sol.get("build_time", 0) + sol.get("runtime", 0)

    rows += [
        ("gurobi", "status", sol["status_str"]),
        ("gurobi", "is_optimal", sol.get("is_optimal", False)),
        ("gurobi", "gap", f"{sol['gap']:.6f}" if sol.get("gap") is not None else "N/A"),
        ("gurobi", "best_bound", f"{sol['best_bound']:.6f}" if sol.get("best_bound") is not None else "N/A"),
        ("gurobi", "solver_time", f"{sol['runtime']:.4f}"),
        ("gurobi", "total_time", f"{total_time:.4f}"),
        ("gurobi", "node_count", sol.get("node_count", 0)),
        ("gurobi", "num_variables", sol["num_variables"]),
        ("gurobi", "num_constraints", sol["num_constraints"]),
        ("gurobi", "stereo_pairs_complete", stereo_complete),
        ("gurobi", "stereo_acq_selected", stereo_acq_selected),
        ("gurobi", "strip_acq_selected", strip_acq_selected),
    ]

    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["section", "metric", "value"])
        w.writerows(rows)

    print(f"  Results  → {path}")


def _write_solution_file(tag: str, sol: dict, results_dir: str) -> None:
    """Write selected acquisition indices (one per line)."""
    if not sol["selected_indices"]:
        return
    path = os.path.join(results_dir, f"Solution_Gurobi_{tag}.txt")
    with open(path, "w") as fh:
        for idx in sorted(sol["selected_indices"]):
            fh.write(f"{idx}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Solve one AEOSSP instance with Gurobi ILP",
    )
    ap.add_argument("tag", help="Instance tag, e.g. 250_8h_1sat")
    ap.add_argument("--instances-dir", default=DEFAULT_INSTANCES_DIR)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    args = ap.parse_args()

    solve_instance(args.tag, args.instances_dir, args.results_dir, args.log_dir)


if __name__ == "__main__":
    main()
