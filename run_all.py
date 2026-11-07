"""Batch runner — solve all 36 AEOSSP instances sequentially."""

import argparse
import csv
import os
import time

from config import DEFAULT_INSTANCES_DIR, DEFAULT_LOG_DIR, DEFAULT_RESULTS_DIR, INSTANCES
from solver import solve_instance


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run Gurobi ILP solver for all AEOSSP instances",
    )
    ap.add_argument("--instances-dir", default=DEFAULT_INSTANCES_DIR)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    ap.add_argument(
        "--tags", nargs="*", default=None,
        help="Subset of instance tags to solve (default: all 36)",
    )
    args = ap.parse_args()

    tags = args.tags if args.tags else sorted(INSTANCES.keys())

    print(f"AEOSSP Gurobi Batch Runner — {len(tags)} instances")
    print(f"  Instances : {os.path.abspath(args.instances_dir)}")
    print(f"  Results   : {os.path.abspath(args.results_dir)}")

    wall_start = time.time()
    summary: list[dict] = []

    for seq, tag in enumerate(tags, 1):
        print(f"\n[{seq}/{len(tags)}] {tag}")
        try:
            sol = solve_instance(
                tag, args.instances_dir, args.results_dir, args.log_dir,
            )
            summary.append({
                "tag": tag,
                "size": INSTANCES[tag]["size"],
                "status": sol["status_str"],
                "objective": sol.get("objective"),
                "gap": sol.get("gap"),
                "runtime": sol["runtime"],
                "selected": sol.get("num_selected", 0),
            })
        except Exception as exc:
            print(f"  ERROR: {exc}")
            summary.append({
                "tag": tag,
                "size": INSTANCES[tag]["size"],
                "status": "ERROR",
                "objective": None,
                "gap": None,
                "runtime": 0.0,
                "selected": 0,
            })

    wall_total = time.time() - wall_start

    # ---- Summary table ----
    hdr = (f"{'Tag':<25} {'|A|':>6} {'Status':<12} "
           f"{'Objective':>14} {'Gap':>8} {'Time':>8} {'Sel':>6}")
    sep = "-" * len(hdr)

    print(f"\n{'=' * len(hdr)}")
    print(f"SUMMARY  —  {len(tags)} instances  —  wall time {wall_total:.0f} s")
    print(f"{'=' * len(hdr)}")
    print(hdr)
    print(sep)

    for r in summary:
        obj = f"{r['objective']:.2f}" if r["objective"] is not None else "N/A"
        gap = f"{r['gap'] * 100:.1f}%" if r["gap"] is not None else "N/A"
        print(f"{r['tag']:<25} {r['size']:>6} {r['status']:<12} "
              f"{obj:>14} {gap:>8} {r['runtime']:>7.1f}s {r['selected']:>6}")

    # ---- Summary CSV ----
    os.makedirs(args.results_dir, exist_ok=True)
    csv_path = os.path.join(args.results_dir, "summary_gurobi.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["tag", "size", "status", "objective",
                        "gap", "runtime", "selected"],
        )
        w.writeheader()
        w.writerows(summary)

    print(f"\nSummary CSV → {csv_path}")


if __name__ == "__main__":
    main()
