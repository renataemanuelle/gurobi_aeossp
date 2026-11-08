"""Compare Gurobi ILP results with RKO metaheuristic results.

Reads the Evaluation_Gurobi_<tag>.csv and the RKO _best / _mean summary
files, then prints (and optionally saves) a side-by-side comparison table.

Usage:
    python3 compare_results.py
    python3 compare_results.py --tags 250_8h_1sat 500_8h_1sat
    python3 compare_results.py --group 250
    python3 compare_results.py --output comparison.csv
"""

import argparse
import csv
import os
from typing import Any, Dict, List, Optional

from config import DEFAULT_RESULTS_DIR, DEFAULT_RKO_RESULTS_DIR, INSTANCES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_section_csv(filepath: str) -> Dict[str, str]:
    """Parse a section,metric,value CSV into a flat dict keyed 'section.metric'."""
    data: Dict[str, str] = {}
    if not os.path.isfile(filepath):
        return data
    with open(filepath, newline="") as fh:
        for row in csv.DictReader(fh):
            sec = row.get("section", "").strip()
            met = row.get("metric", "").strip()
            val = row.get("value", "").strip()
            if sec and met:
                data[f"{sec}.{met}"] = val
    return data


def _safe_float(d: Dict[str, str], key: str) -> Optional[float]:
    """Extract a float from the dict, returning None on failure."""
    val = d.get(key)
    if val is None or val in ("", "N/A"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _fmt(val: Optional[float], decimals: int = 4) -> str:
    if val is None:
        return "—"
    return f"{val:.{decimals}f}"


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.2f}%"


def _read_gurobi(tag: str, grb_dir: str) -> Dict[str, Any]:
    """Read Gurobi evaluation for one instance."""
    d = _read_section_csv(os.path.join(grb_dir, f"Evaluation_Gurobi_{tag}.csv"))
    return {
        "obj": _safe_float(d, "solution.total_score"),
        "gap": _safe_float(d, "gurobi.gap"),
        "status": d.get("gurobi.status"),
        "time": _safe_float(d, "gurobi.solver_time"),
        "selected": _safe_float(d, "solution.acquisitions"),
        "is_optimal": d.get("gurobi.is_optimal"),
    }


def _read_rko(tag: str, rko_dir: str) -> Dict[str, Any]:
    """Read RKO best and mean summary files for one instance."""
    best = _read_section_csv(os.path.join(rko_dir, f"Evaluation_RKO_{tag}_best.csv"))
    mean = _read_section_csv(os.path.join(rko_dir, f"Evaluation_RKO_{tag}_mean.csv"))
    return {
        "best_obj": _safe_float(best, "solution.total_score"),
        "best_sel": _safe_float(best, "solution.acquisitions"),
        "best_time": _safe_float(best, "rko.solver_time"),
        "mean_obj": _safe_float(mean, "solution.total_score"),
        "mean_sel": _safe_float(mean, "solution.acquisitions"),
        "mean_time": _safe_float(mean, "rko.solver_time"),
    }


def _resolve_tags(args) -> List[str]:
    """Build the sorted list of instance tags from CLI arguments."""
    tags: List[str] = []

    if args.tags:
        tags.extend(t for t in args.tags if t in INSTANCES)

    if args.group:
        for prefix in args.group:
            tags.extend(t for t in INSTANCES if t.startswith(prefix))

    if not tags:
        tags = list(INSTANCES.keys())

    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return sorted(unique, key=lambda t: INSTANCES[t]["size"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Compare Gurobi vs RKO results")
    ap.add_argument("tags", nargs="*", default=None,
                    help="Instance tags to compare")
    ap.add_argument("--group", nargs="*", default=None,
                    help="Compare all instances with given prefix(es)")
    ap.add_argument("--gurobi-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--rko-dir", default=DEFAULT_RKO_RESULTS_DIR)
    ap.add_argument("--output", default=None, help="Save comparison CSV")
    args = ap.parse_args()

    tags = _resolve_tags(args)

    hdr = (f"{'Tag':<22} {'|A|':>5} "
           f"{'Gurobi':>10} {'Gap':>8} {'Status':>9} {'Time':>8} "
           f"{'RKO Best':>10} {'RKO Mean':>10} {'RKO T':>8} "
           f"{'G/Rbest':>8}")
    sep = "─" * len(hdr)

    print(sep)
    print(hdr)
    print(sep)

    rows: List[dict] = []
    n_better = n_equal = n_worse = n_missing = 0

    for tag in tags:
        size = INSTANCES[tag]["size"]
        g = _read_gurobi(tag, args.gurobi_dir)
        r = _read_rko(tag, args.rko_dir)

        # Compute ratio Gurobi / RKO best
        ratio = None
        if g["obj"] is not None and r["best_obj"] is not None and r["best_obj"] > 0:
            ratio = g["obj"] / r["best_obj"]

        # Track comparison counts
        if g["obj"] is None or r["best_obj"] is None:
            n_missing += 1
            marker = " "
        elif abs(g["obj"] - r["best_obj"]) < 1e-6:
            n_equal += 1
            marker = "="
        elif g["obj"] > r["best_obj"]:
            n_better += 1
            marker = "▲"
        else:
            n_worse += 1
            marker = "▼"

        print(
            f"{tag:<22} {size:>5} "
            f"{_fmt(g['obj'], 4):>10} {_fmt_pct(g['gap']):>8} "
            f"{(g['status'] or '—'):>9} {_fmt(g['time'], 1):>7}s "
            f"{_fmt(r['best_obj'], 4):>10} {_fmt(r['mean_obj'], 4):>10} "
            f"{_fmt(r['best_time'], 1):>7}s "
            f"{_fmt(ratio, 4):>8} {marker}"
        )

        rows.append({
            "tag": tag,
            "size": size,
            "gurobi_obj": _fmt(g["obj"], 6),
            "gurobi_gap": _fmt(g["gap"], 6),
            "gurobi_status": g["status"] or "",
            "gurobi_time": _fmt(g["time"], 4),
            "gurobi_selected": _fmt(g["selected"], 0),
            "rko_best_obj": _fmt(r["best_obj"], 6),
            "rko_mean_obj": _fmt(r["mean_obj"], 6),
            "rko_best_time": _fmt(r["best_time"], 4),
            "ratio": _fmt(ratio, 6),
        })

    print(sep)
    total = len(tags)
    compared = n_better + n_equal + n_worse
    print(f"  {total} instances  |  {compared} compared: "
          f"▲ Gurobi better {n_better}  |  = Equal {n_equal}  |  "
          f"▼ RKO better {n_worse}  |  — Missing {n_missing}")

    if args.output:
        with open(args.output, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  Comparison saved → {args.output}")


if __name__ == "__main__":
    main()
