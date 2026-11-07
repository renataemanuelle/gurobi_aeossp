"""Configuration for the AEOSSP Gurobi ILP solver.

Paths, instance definitions, and physical constants.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Paths — override with environment variables or CLI arguments
# ---------------------------------------------------------------------------
# Default relative paths assume this repo lives at:
#   ~/Desktop/renata/gurobi/gurobi_aeossp/
# and the RKO framework is at:
#   ~/Desktop/renata/RKO-solver-Framework_v2.0/

DEFAULT_INSTANCES_DIR = os.environ.get(
    "AEOSSP_INSTANCES_DIR",
    os.path.join(PROJECT_DIR, "..", "..", "RKO-solver-Framework_v2.0", "Instances"),
)

DEFAULT_RESULTS_DIR = os.environ.get(
    "AEOSSP_RESULTS_DIR",
    os.path.join(PROJECT_DIR, "Results"),
)

DEFAULT_RKO_RESULTS_DIR = os.environ.get(
    "AEOSSP_RKO_RESULTS_DIR",
    os.path.join(PROJECT_DIR, "..", "..", "RKO-solver-Framework_v2.0", "Results_linux"),
)

DEFAULT_LOG_DIR = os.environ.get(
    "AEOSSP_LOG_DIR",
    os.path.join(PROJECT_DIR, "Logs"),
)

# ---------------------------------------------------------------------------
# Physical constants (matching the C++ decoder in Problem.h)
# ---------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0
SATELLITE_ALTITUDE_KM = 550.0
SLEW_RATE_DEG_PER_SEC = 2.5          # 30° in 12 s
STEREO_ORBIT_THRESHOLD_SEC = 600.0   # min epoch gap for different orbits

# ---------------------------------------------------------------------------
# Instance catalogue — tag → {size, maxtime}
# size  = |A| (number of acquisition rows in the CSV)
# maxtime = Gurobi TimeLimit in seconds
# ---------------------------------------------------------------------------
INSTANCES = {
    "250_8h_1sat":   {"size": 191,   "maxtime": 60},
    "250_8h_2sat":   {"size": 362,   "maxtime": 60},
    "250_8h_3sat":   {"size": 578,   "maxtime": 60},
    "250_8h_4sat":   {"size": 733,   "maxtime": 60},
    "250_12h_1sat":  {"size": 214,   "maxtime": 60},
    "250_12h_2sat":  {"size": 401,   "maxtime": 60},
    "250_12h_3sat":  {"size": 627,   "maxtime": 60},
    "250_12h_4sat":  {"size": 855,   "maxtime": 60},
    "250_24h_1sat":  {"size": 718,   "maxtime": 60},
    "250_24h_2sat":  {"size": 1404,  "maxtime": 150},
    "250_24h_3sat":  {"size": 2219,  "maxtime": 300},
    "250_24h_4sat":  {"size": 2891,  "maxtime": 300},
    "500_8h_1sat":   {"size": 383,   "maxtime": 60},
    "500_8h_2sat":   {"size": 737,   "maxtime": 60},
    "500_8h_3sat":   {"size": 1196,  "maxtime": 150},
    "500_8h_4sat":   {"size": 1550,  "maxtime": 150},
    "500_12h_1sat":  {"size": 416,   "maxtime": 60},
    "500_12h_2sat":  {"size": 791,   "maxtime": 60},
    "500_12h_3sat":  {"size": 1300,  "maxtime": 150},
    "500_12h_4sat":  {"size": 1737,  "maxtime": 150},
    "500_24h_1sat":  {"size": 1331,  "maxtime": 150},
    "500_24h_2sat":  {"size": 2651,  "maxtime": 300},
    "500_24h_3sat":  {"size": 4307,  "maxtime": 600},
    "500_24h_4sat":  {"size": 5546,  "maxtime": 600},
    "1000_8h_1sat":  {"size": 930,   "maxtime": 60},
    "1000_8h_2sat":  {"size": 1750,  "maxtime": 150},
    "1000_8h_3sat":  {"size": 2629,  "maxtime": 300},
    "1000_8h_4sat":  {"size": 3513,  "maxtime": 600},
    "1000_12h_1sat": {"size": 999,   "maxtime": 60},
    "1000_12h_2sat": {"size": 1870,  "maxtime": 150},
    "1000_12h_3sat": {"size": 2872,  "maxtime": 300},
    "1000_12h_4sat": {"size": 3912,  "maxtime": 600},
    "1000_24h_1sat": {"size": 2755,  "maxtime": 300},
    "1000_24h_2sat": {"size": 5516,  "maxtime": 600},
    "1000_24h_3sat": {"size": 8733,  "maxtime": 900},
    "1000_24h_4sat": {"size": 11353, "maxtime": 900},
}
