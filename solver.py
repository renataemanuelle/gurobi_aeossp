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
    time_limit = cfg["maxtime"]

    print(f"\n{'=' * 64}")
    print(f"  Instance : {tag}   |A| = {cfg['size']}   TimeLimit = {time_limit} s")
    print(f"{'=' * 64}")

    acquisitions = parse_instance(tag, instances_dir)
    print(f"  Loaded {len(acquisitions)} acquisitions from CSV")

    log_file = None
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"gurobi_{tag}.log")

    solution = build_and_solve(acquisitions, time_limit, log_file)

    os.makedirs(results_dir, exist_ok=True)
    _write_evaluation_csv(tag, cfg, solution, results_dir)
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
    tag: str, cfg: dict, sol: dict, results_dir: str
) -> None:
    """Write Evaluation_Gurobi_<tag>.csv in section,metric,value format."""
    path = os.path.join(results_dir, f"Evaluation_Gurobi_{tag}.csv")

    rows = [
        ("INSTANCE", "tag", tag),
        ("INSTANCE", "num_acquisitions", cfg["size"]),
        ("INSTANCE", "time_limit_seconds", cfg["maxtime"]),
        ("SOLVER", "name", "Gurobi"),
        ("SOLVER", "version", sol.get("gurobi_version", "")),
        ("SOLVER", "status", sol["status_str"]),
        ("SOLVER", "is_optimal", sol["is_optimal"]),
        ("SOLVER", "runtime_seconds", f"{sol['runtime']:.4f}"),
        ("SOLVER", "build_time_seconds", f"{sol['build_time']:.4f}"),
        ("SOLVER", "node_count", sol.get("node_count", "")),
        ("MODEL", "num_variables", sol["num_variables"]),
        ("MODEL", "num_constraints", sol["num_constraints"]),
        ("MODEL", "num_request_constraints", sol["num_request_constraints"]),
        ("MODEL", "num_conflict_constraints", sol["num_conflict_constraints"]),
        ("MODEL", "num_stereo_constraints", sol["num_stereo_constraints"]),
    ]

    if sol["objective"] is not None:
        rows += [
            ("SOLUTION", "objective_value", f"{sol['objective']:.6f}"),
            ("SOLUTION", "best_bound", f"{sol['best_bound']:.6f}"),
            ("SOLUTION", "gap", f"{sol['gap']:.6f}"),
            ("SOLUTION", "num_selected_acquisitions", sol["num_selected"]),
        ]
    else:
        rows += [
            ("SOLUTION", "objective_value", "N/A"),
            ("SOLUTION", "best_bound", "N/A"),
            ("SOLUTION", "gap", "N/A"),
            ("SOLUTION", "num_selected_acquisitions", 0),
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
