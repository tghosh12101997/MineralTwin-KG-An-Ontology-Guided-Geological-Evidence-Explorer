from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
GEMPY_DIR = DATA_DIR / "gempy"

MAIN_WORKBOOK = RAW_DIR / "australian_mineral_deposits.xlsx"
DEPOSIT_CLASSIFICATION = RAW_DIR / "deposit_classification.xlsx"
MINERAL_ABBREVIATIONS = RAW_DIR / "mineral_abbreviations.xlsx"
TECTONIC_PROVINCES = RAW_DIR / "tectonic_provinces.xlsx"
COMMODITY_ENDOWMENT = RAW_DIR / "commodity_endowment_calculations.xlsx"
OCCURRENCES_GEOJSON = RAW_DIR / "mineral_occurrences_sample.geojson"

REQUIRED_FILES = (
    MAIN_WORKBOOK,
    DEPOSIT_CLASSIFICATION,
    MINERAL_ABBREVIATIONS,
    TECTONIC_PROVINCES,
    COMMODITY_ENDOWMENT,
    OCCURRENCES_GEOJSON,
)

TARGET_COMMODITIES = ("Li", "Cu", "Ni")
SAMPLE_SIZE = 50
