"""Batch runner — solve selected AEOSSP instances sequentially.

Usage examples
--------------
    python3 run_all.py 250_8h_1sat 250_8h_2sat     # specific tags
    python3 run_all.py --group 250_8h               # all tags starting with prefix
    python3 run_all.py --group 250                   # broader prefix
    python3 run_all.py --list                        # show available instances
    python3 run_all.py --all                         # run every instance
"""

import argparse
import csv
import os
import sys
import time
from typing import List

from config import DEFAULT_INSTANCES_DIR, DEFAULT_LOG_DIR, DEFAULT_RESULTS_DIR, INSTANCES
from solver import solve_instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sorted_by_size(tags: List[str]) -> List[str]:
    """Return tags sorted by |A| (ascending)."""
    return sorted(tags, key=lambda t: INSTANCES[t]["size"])


def _format_time(seconds: float) -> str:
    """Human-readable elapsed time (s / min / h)."""
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.2f} h"


def _resolve_tags(args) -> List[str]:
    """Build the list of instance tags from CLI arguments."""
    tags: List[str] = []

    # Positional tags
    if args.tags:
        for t in args.tags:
            if t not in INSTANCES:
                print(f"WARNING: unknown tag '{t}' — skipping")
            else:
                tags.append(t)

    # --group prefixes
    if args.group:
        for prefix in args.group:
            matched = [t for t in INSTANCES if t.startswith(prefix)]
            if not matched:
                print(f"WARNING: no instances match prefix '{prefix}'")
            tags.extend(matched)

    # --all
    if args.all:
        tags = list(INSTANCES.keys())

    # Deduplicate preserving first occurrence order
    seen = set()
    unique: List[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return _sorted_by_size(unique)


def _list_instances() -> None:
    """Print a table of available instances sorted by |A|."""
    tags = _sorted_by_size(list(INSTANCES.keys()))
    print(f"\nAvailable instances ({len(tags)}):\n")
    print(f"  {'Tag':<25} {'|A|':>6}")
    print(f"  {'-' * 25} {'-' * 6}")
    for t in tags:
        print(f"  {t:<25} {INSTANCES[t]['size']:>6}")
    print()


def _load_existing_summary(csv_path: str) -> dict:
    """Load existing summary CSV into a dict keyed by tag."""
    existing = {}
    if os.path.isfile(csv_path):
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                existing[row["tag"]] = row
    return existing


def _write_summary_csv(csv_path: str, rows: List[dict]) -> None:
    """Write (or overwrite) the summary CSV, sorted by |A|."""
    fieldnames = ["tag", "size", "status", "objective", "gap",
                  "runtime", "runtime_fmt", "selected"]
    rows_sorted = sorted(rows, key=lambda r: int(r["size"]))

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_sorted)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run Gurobi ILP solver for AEOSSP instances",
        epilog="Examples:\n"
               "  python3 run_all.py 250_8h_1sat 250_8h_2sat\n"
               "  python3 run_all.py --group 250_8h\n"
               "  python3 run_all.py --group 250\n"
               "  python3 run_all.py --list\n"
               "  python3 run_all.py --all\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "tags", nargs="*", default=None,
        help="Instance tags to solve (e.g. 250_8h_1sat 250_8h_2sat)",
    )
    ap.add_argument(
        "--group", nargs="*", default=None,
        help="Solve all instances whose tag starts with the given prefix(es)",
    )
    ap.add_argument(
        "--all", action="store_true",
        help="Solve all 36 instances",
    )
    ap.add_argument(
        "--list", action="store_true", dest="list_instances",
        help="List available instances and exit",
    )
    ap.add_argument("--instances-dir", default=DEFAULT_INSTANCES_DIR)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    args = ap.parse_args()

    # --list: show and exit
    if args.list_instances:
        _list_instances()
        sys.exit(0)

    # Resolve which tags to run
    tags = _resolve_tags(args)
    if not tags:
        print("No instances selected. Use --list to see available tags, "
              "or --all to run everything.")
        sys.exit(1)

    print(f"AEOSSP Gurobi Batch Runner — {len(tags)} instance(s)  (exact — no time limit)")
    print(f"  Instances : {os.path.abspath(args.instances_dir)}")
    print(f"  Results   : {os.path.abspath(args.results_dir)}")

    wall_start = time.time()
    new_results: list[dict] = []

    for seq, tag in enumerate(tags, 1):
        print(f"\n[{seq}/{len(tags)}] {tag}")
        try:
            sol = solve_instance(
                tag, args.instances_dir, args.results_dir, args.log_dir,
            )
            runtime = sol["runtime"]
            new_results.append({
                "tag": tag,
                "size": INSTANCES[tag]["size"],
                "status": sol["status_str"],
                "objective": sol.get("objective"),
                "gap": sol.get("gap"),
                "runtime": runtime,
                "runtime_fmt": _format_time(runtime),
                "selected": sol.get("num_selected", 0),
            })
        except Exception as exc:
            print(f"  ERROR: {exc}")
            new_results.append({
                "tag": tag,
                "size": INSTANCES[tag]["size"],
                "status": "ERROR",
                "objective": None,
                "gap": None,
                "runtime": 0.0,
                "runtime_fmt": "0.0 s",
                "selected": 0,
            })

    wall_total = time.time() - wall_start

    # ---- Summary table (terminal) ----
    hdr = (f"{'Tag':<25} {'|A|':>6} {'Status':<12} "
           f"{'Objective':>14} {'Gap':>8} {'Time':>12} {'Sel':>6}")
    sep = "-" * len(hdr)

    print(f"\n{'=' * len(hdr)}")
    print(f"SUMMARY  —  {len(tags)} instance(s)  —  wall time {_format_time(wall_total)}")
    print(f"{'=' * len(hdr)}")
    print(hdr)
    print(sep)

    for r in new_results:
        obj = f"{r['objective']:.2f}" if r["objective"] is not None else "N/A"
        gap = f"{r['gap'] * 100:.1f}%" if r["gap"] is not None else "N/A"
        print(f"{r['tag']:<25} {r['size']:>6} {r['status']:<12} "
              f"{obj:>14} {gap:>8} {r['runtime_fmt']:>12} {r['selected']:>6}")

    # ---- Accumulate into summary CSV ----
    os.makedirs(args.results_dir, exist_ok=True)
    csv_path = os.path.join(args.results_dir, "summary_gurobi.csv")

    existing = _load_existing_summary(csv_path)
    for r in new_results:
        existing[r["tag"]] = r
    _write_summary_csv(csv_path, list(existing.values()))

    print(f"\nSummary CSV → {csv_path}  ({len(existing)} total entries)")


if __name__ == "__main__":
    main()
