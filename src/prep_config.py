"""Paths and thresholds for the data-preparation step (separate from the project config.py)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

RAW = DATA / "raw"                       # never edited
TEXT = DATA / "text"                     # output of src/extract/extractor.py
TEXT_CLEAN = DATA / "text_clean"         # output of src/extract/prepare.py
PROVENANCE = DATA / "provenance.csv"
NOMENCLATURE_XLSX = DATA / "medicaments_40.xlsx"

CLEAN_DOCS_CSV = DATA / "clean_docs.csv"
REJECTED_CSV = DATA / "rejected.csv"
NOMENCLATURE_CLEAN_CSV = DATA / "medicaments_clean.csv"
REPORTS = ROOT / "reports"

# filtering thresholds
MIN_CHARS = 300          # shorter text = empty / failed extraction
MAX_GARBAGE = 0.25       # share of weird characters = bad OCR
MAX_DOSE_MG = 10_000     # a single dose above this is flagged as outlier

# authority level (1 = most reliable) - folder name under data/raw/
AUTHORITY = {"anpp": 1, "nomenclature": 2, "dailymed": 3, "ansm": 3, "ema": 3}
DEFAULT_AUTHORITY = 5
