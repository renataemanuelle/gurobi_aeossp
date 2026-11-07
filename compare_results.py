"""Compare Gurobi ILP results with RKO metaheuristic results.

Reads the Evaluation_Gurobi_*.csv files from Results/ and the
Evaluation_RKO_*.csv files from the RKO Results_linux/ directory,
then prints (and optionally saves) a side-by-side comparison table.
"""

import argparse
import csv
import glob
import os
from typing import Any, Dict, List, Optional

from config import DEFAULT_RESULTS_DIR, DEFAULT_RKO_RESULTS_DIR, INSTANCES


def _read_section_csv(filepath: str) -> Dict[str, str]:
    """Parse a section,metric,value CSV into a flat dict keyed 'section.metric'."""
    data: Dict[str, str] = {}
    with open(filepath, newline="") as fh:
        for row in csv.DictReader(fh):
            sec = row.get("section", "").strip()
            met = row.get("metric", "").strip()
            val = row.get("value", "").strip()
            if sec and met:
                data[f"{sec}.{met}"] = val
    return data


_RKO_OBJ_KEYS = [
    "SOLUTION.objective_value",
    "RESULT.best_solution",
    "SOLUTION.best_solution",
    "RESULT.BestSol",
    "SOLUTION.BestSol",
    "RESULT.objective",
    "SOLUTION.total_score",
    "RESULT.best",
]


def _read_rko(tag: str, rko_dir: str) -> Optional[Dict[str, Any]]:
    """Aggregate RKO results across seeds for one instance."""
    pattern = os.path.join(rko_dir, f"Evaluation_RKO_{tag}_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        pattern = os.path.join(rko_dir, f"*{tag}*.csv")
        files = sorted(glob.glob(pattern))
    if not files:
        return None

    objectives: List[float] = []
    for fp in files:
        d = _read_section_csv(fp)
        for k in _RKO_OBJ_KEYS:
            if k in d:
                try:
                    objectives.append(float(d[k]))
                except (ValueError, TypeError):
                    pass
                break

    if not objectives:
        return {"files": len(files)}

    return {
        "files": len(files),
        "best": max(objectives),
        "worst": min(objectives),
        "avg": sum(objectives) / len(objectives),
    }


def _read_gurobi(tag: str, grb_dir: str) -> Optional[Dict[str, str]]:
    fp = os.path.join(grb_dir, f"Evaluation_Gurobi_{tag}.csv")
    if not os.path.isfile(fp):
        return None
    d = _read_section_csv(fp)
    return {k.split(".", 1)[1]: v for k, v in d.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare Gurobi vs RKO results")
    ap.add_argument("--gurobi-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--rko-dir", default=DEFAULT_RKO_RESULTS_DIR)
    ap.add_argument("--tags", nargs="*", default=None)
    ap.add_argument("--output", default=None, help="Save comparison CSV")
    args = ap.parse_args()

    tags = args.tags if args.tags else sorted(INSTANCES.keys())

    hdr = (f"{'Tag':<25} {'|A|':>6} {'Gurobi Obj':>14} {'Gap':>8} "
           f"{'Status':>10} {'RKO Best':>14} {'RKO Avg':>14} {'G/R':>8}")
    sep = "-" * len(hdr)
    print(hdr)
    print(sep)

    rows: list[dict] = []

    for tag in tags:
        grb = _read_gurobi(tag, args.gurobi_dir)
        rko = _read_rko(tag, args.rko_dir)

        g_obj = grb.get("objective_value", "—") if grb else "—"
        g_gap = grb.get("gap", "—") if grb else "—"
        g_st = grb.get("status", "—") if grb else "—"
        r_best = f"{rko['best']:.2f}" if rko and "best" in rko else "—"
        r_avg = f"{rko['avg']:.2f}" if rko and "avg" in rko else "—"

        ratio = "—"
        try:
            gv = float(g_obj)
            rv = rko["best"] if rko and "best" in rko else None
            if rv and rv > 0:
                ratio = f"{gv / rv:.4f}"
        except (ValueError, TypeError):
            pass

        print(f"{tag:<25} {INSTANCES[tag]['size']:>6} {g_obj:>14} "
              f"{g_gap:>8} {g_st:>10} {r_best:>14} {r_avg:>14} {ratio:>8}")

        rows.append({
            "tag": tag,
            "size": INSTANCES[tag]["size"],
            "gurobi_obj": g_obj,
            "gurobi_gap": g_gap,
            "gurobi_status": g_st,
            "rko_best": r_best,
            "rko_avg": r_avg,
            "ratio": ratio,
        })

    if args.output:
        with open(args.output, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nComparison saved → {args.output}")


if __name__ == "__main__":
    main()
