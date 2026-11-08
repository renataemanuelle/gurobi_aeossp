"""Parse AEOSSP instance CSV files into structured acquisition data."""

import math
import os
import re
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd

from config import EARTH_RADIUS_KM, SATELLITE_ALTITUDE_KM


@dataclass
class Acquisition:
    """One acquisition opportunity (one row of the dedup'd _pf_df.csv)."""

    idx: int            # index (position in the dedup'd list, like RKO)
    row_pos: int        # same as idx after dedup
    req_id: str         # request ID (grouping key)
    stereo: int         # stereo requirement (0 = mono, 1 = stereo — binarised)
    satellite: str      # satellite identifier
    sat_lat: float      # satellite sub-point latitude  (degrees)
    sat_lon: float      # satellite sub-point longitude (degrees)
    req_lat: float      # request location latitude  (degrees)
    req_lon: float      # request location longitude (degrees)
    time: float         # epoch of acquisition start (POSIX seconds)
    strips: int         # number of strips for this request
    duration: float     # acquisition duration (seconds)
    score: float        # score_scenario — objective coefficient
    # Extra CSV fields for evaluation metrics
    area: float = 0.0
    angle: float = 0.0
    price: float = 0.0
    sun_elevation: float = 0.0
    cloud_cover_estimate: float = 0.0
    cloud_cover_real: float = 0.0
    priority: int = 0
    # Pre-computed 3D cartesian positions (populated by compute_cartesian)
    sat_x: float = 0.0
    sat_y: float = 0.0
    sat_z: float = 0.0
    req_x: float = 0.0
    req_y: float = 0.0
    req_z: float = 0.0


def compute_cartesian(
    acq: Acquisition,
    satellite_altitude_km: float = SATELLITE_ALTITUDE_KM,
) -> None:
    """Populate sat_x/y/z and req_x/y/z from lat/lon (matches RKO cart_system)."""
    R = EARTH_RADIUS_KM
    h = satellite_altitude_km

    lat_s = math.radians(acq.sat_lat)
    lon_s = math.radians(acq.sat_lon)
    acq.sat_x = (R + h) * math.cos(lat_s) * math.cos(lon_s)
    acq.sat_y = (R + h) * math.cos(lat_s) * math.sin(lon_s)
    acq.sat_z = (R + h) * math.sin(lat_s)

    lat_r = math.radians(acq.req_lat)
    lon_r = math.radians(acq.req_lon)
    acq.req_x = R * math.cos(lat_r) * math.cos(lon_r)
    acq.req_y = R * math.cos(lat_r) * math.sin(lon_r)
    acq.req_z = R * math.sin(lat_r)


def _parse_location(loc_str: str) -> Tuple[float, float]:
    """Extract (lat, lon) from a location column value.

    Handles common CSV encodings including np.float64() wrappers:
      "[57.467, 3.631]", "[np.float64(55.149), np.float64(-1.225)]"
    """
    cleaned = re.sub(r"np\.float64\(([^)]+)\)", r"\1", str(loc_str))
    cleaned = re.sub(r"[\[\]()'\"{} ]", " ", cleaned)
    parts = re.split(r"[,;\s]+", cleaned.strip())
    parts = [p for p in parts if p]

    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse location '{loc_str}': need ≥ 2 numeric values, got {parts}"
        )

    return float(parts[0]), float(parts[1])


def parse_instance(
    tag: str, instances_dir: str,
) -> Tuple[List[Acquisition], pd.DataFrame]:
    """Load an AEOSSP instance from its CSV file.

    Performs stereo binarisation and deduplication (matching the RKO pipeline).

    Args:
        tag: Instance tag, e.g. "250_8h_1sat".
        instances_dir: Directory containing the instance files.

    Returns:
        (acquisitions, df_raw) — dedup'd Acquisition list and the raw DataFrame.
    """
    csv_path = os.path.join(instances_dir, f"eoss_instance_{tag}_pf_df.csv")

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Instance CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    required = [
        "index", "ID", "stereo", "satellite", "satellite location",
        "request location", "time", "area", "strips", "duration",
        "distance", "angle", "sun elevation", "cloud cover estimate",
        "priority", "price", "cloud cover real", "score_scenario",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns in {csv_path}: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

    # Keep a raw copy for scenario_raw metrics
    df_raw = df.copy()

    # Binarise stereo (like RKO: any stereo > 0 → 1)
    df["stereo"] = df["stereo"].apply(lambda s: 1 if int(s) > 0 else 0)

    # Deduplicate by (ID, satellite, time, satellite location) — matches RKO
    df = (
        df.drop_duplicates(
            subset=["ID", "satellite", "time", "satellite location"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    # Convert time column to POSIX epoch seconds
    time_dt = pd.to_datetime(df["time"])
    time_seconds = time_dt.astype("int64") / 1e9

    acquisitions: List[Acquisition] = []

    for row_pos, (_, row) in enumerate(df.iterrows()):
        sat_lat, sat_lon = _parse_location(row["satellite location"])
        req_lat, req_lon = _parse_location(row["request location"])

        acq = Acquisition(
            idx=row_pos,
            row_pos=row_pos,
            req_id=str(row["ID"]).strip(),
            stereo=int(row["stereo"]),
            satellite=str(row["satellite"]).strip(),
            sat_lat=sat_lat,
            sat_lon=sat_lon,
            req_lat=req_lat,
            req_lon=req_lon,
            time=float(time_seconds.iloc[row_pos]),
            strips=int(row["strips"]),
            duration=float(row["duration"]),
            score=float(row["score_scenario"]),
            area=float(row["area"]),
            angle=float(row["angle"]),
            price=float(row["price"]),
            sun_elevation=float(row["sun elevation"]),
            cloud_cover_estimate=float(row["cloud cover estimate"]),
            cloud_cover_real=float(row["cloud cover real"]),
            priority=int(row["priority"]),
        )
        compute_cartesian(acq)
        acquisitions.append(acq)

    return acquisitions, df_raw
