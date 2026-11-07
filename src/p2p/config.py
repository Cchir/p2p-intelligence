"""Project paths and constants. Everything is relative to the repository root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
WAREHOUSE = DATA / "warehouse"
DB_PATH = WAREHOUSE / "p2p.duckdb"
DBT_DIR = ROOT / "dbt"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
SERVING = ROOT / "dashboard" / "data"

SOURCE_URL = "https://data.4tu.nl/file/35ed7122-966a-484e-a0e1-749b64e3366d/864493d1-3a58-47f6-ad6f-27f95f995828"
SOURCE_MD5 = "4eb909242351193a61e1c15b9c3cc814"
SOURCE_XES = RAW / "BPI_Challenge_2019.xes"
BRONZE_CASES = RAW / "bronze_cases.parquet"
BRONZE_EVENTS = RAW / "bronze_events.parquet"


def ensure_dirs() -> None:
    for p in (RAW, WAREHOUSE, REPORTS, FIGURES):
        p.mkdir(parents=True, exist_ok=True)
