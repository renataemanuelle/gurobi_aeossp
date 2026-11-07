"""Parse AEOSSP instance CSV files into structured acquisition data."""

import os
import re
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd


@dataclass
class Acquisition:
    """One acquisition opportunity (one row of the _pf_df.csv)."""

    idx: int            # original 'index' column from CSV
    row_pos: int        # 0-based position in the loaded list
    req_id: str         # request ID (grouping key)
    stereo: int         # stereo requirement (0 = mono)
    satellite: str      # satellite identifier
    sat_lat: float      # satellite sub-point latitude  (degrees)
    sat_lon: float      # satellite sub-point longitude (degrees)
    time: float         # epoch of acquisition start (seconds)
    strips: int         # number of strips for this request
    duration: float     # acquisition duration (seconds)
    score: float        # score_scenario — objective coefficient


def _parse_location(loc_str: str) -> Tuple[float, float]:
    """Extract (lat, lon) from a location column value.

    Handles common CSV encodings:
      "(lat, lon)", "[lat lon]", "lat lon", "lat,lon", "lat;lon"
    If three values are present the third (altitude) is discarded.
    """
    cleaned = re.sub(r"[\[\]()'\"{} ]", " ", str(loc_str))
    parts = re.split(r"[,;\s]+", cleaned.strip())
    parts = [p for p in parts if p]

    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse location '{loc_str}': need ≥ 2 numeric values, got {parts}"
        )

    return float(parts[0]), float(parts[1])


def parse_instance(tag: str, instances_dir: str) -> List[Acquisition]:
    """Load an AEOSSP instance from its CSV file.

    Args:
        tag: Instance tag, e.g. "250_8h_1sat".
        instances_dir: Directory containing the instance files.

    Returns:
        Ordered list of Acquisition objects.
    """
    csv_path = os.path.join(instances_dir, f"eoss_instance_{tag}_pf_df.csv")

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Instance CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    required = [
        "index", "ID", "stereo", "satellite", "satellite location",
        "time", "strips", "duration", "score_scenario",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns in {csv_path}: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

    acquisitions: List[Acquisition] = []

    for row_pos, (_, row) in enumerate(df.iterrows()):
        sat_lat, sat_lon = _parse_location(row["satellite location"])
        acq = Acquisition(
            idx=int(row["index"]),
            row_pos=row_pos,
            req_id=str(row["ID"]).strip(),
            stereo=int(row["stereo"]),
            satellite=str(row["satellite"]).strip(),
            sat_lat=sat_lat,
            sat_lon=sat_lon,
            time=float(row["time"]),
            strips=int(row["strips"]),
            duration=float(row["duration"]),
            score=float(row["score_scenario"]),
        )
        acquisitions.append(acq)

    return acquisitions
