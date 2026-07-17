from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .config import (
    DEPOSIT_CLASSIFICATION,
    MAIN_WORKBOOK,
    MINERAL_ABBREVIATIONS,
    OCCURRENCES_GEOJSON,
    PROCESSED_DIR,
    REQUIRED_FILES,
    SAMPLE_SIZE,
    TARGET_COMMODITIES,
    TECTONIC_PROVINCES,
)


MAIN_SHEET = "Australia"

BASE_COLUMNS = [
    "Deposit",
    "Principal deposit environment",
    "Principal deposit group",
    "Principal deposit type",
    "ENO",
    "MINLOCNO",
    "State",
    "Longitude",
    "Latitude",
    "District",
    "Element",
    "Province",
    "Subprovince",
    "Zone",
    "CRIRSCO-compliant",
    "Major/co-products",
    "Known by-products (10-20%)",
    "Known by-products (<10%)",
    "Potential by-products",
    "Regional alteration assemblages",
    "Proximal alteration assemblages",
    "Alteration assemblage group",
    "Source(s) of data - location",
    "Source(s) of data - geology",
    "Source(s) of data - age",
    "Source(s) of data - resources/endowment",
    "Comments",
]

GRADE_COLUMNS = {
    "Li": "Li2O (%)",
    "Cu": "Cu (%)",
    "Ni": "Ni (%)",
}

ENDOWMENT_COLUMNS = {
    "Li": "Li (Mt)",
    "Cu": "Cu (Mt)",
    "Ni": "Ni (Mt)",
}

COMMODITY_COLUMNS = [
    "Major/co-products",
    "Known by-products (10-20%)",
    "Known by-products (<10%)",
    "Potential by-products",
]


@dataclass(frozen=True)
class PipelineOutputs:
    deposits_clean: Path
    deposits_sample: Path
    host_rocks: Path
    igneous_rocks: Path
    alterations: Path
    occurrences_geojson: Path
    quality_report: Path


def validate_input_files(paths: Iterable[Path] = REQUIRED_FILES) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        joined = "\n  - ".join(missing)
        raise FileNotFoundError(
            "Required project files are missing:\n"
            f"  - {joined}\n\n"
            "Place the files in data/raw using the filenames shown above."
        )


def slugify(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def clean_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def tokenize_commodities(value: Any) -> set[str]:
    text = clean_text(value)
    if not text:
        return set()

    normalized = (
        text.replace("±", "-")
        .replace("/", "-")
        .replace(";", "-")
        .replace(",", "-")
        .replace("&", "-")
    )
    return {
        token.strip()
        for token in re.split(r"[-\s]+", normalized)
        if token.strip()
    }


def _stable_deposit_id(row: pd.Series) -> str:
    eno = row.get("ENO")
    if pd.notna(eno):
        try:
            return f"deposit-{int(float(eno))}"
        except (TypeError, ValueError):
            pass
    return f"deposit-{slugify(row.get('Deposit'))}"


def _available_columns(frame: pd.DataFrame, requested: Iterable[str]) -> list[str]:
    return [column for column in requested if column in frame.columns]


def load_main_deposits(path: Path = MAIN_WORKBOOK) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=MAIN_SHEET, engine="openpyxl")
    frame.columns = [str(column).strip() for column in frame.columns]

    required = {"Deposit", "Longitude", "Latitude", "Major/co-products"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Main workbook is missing expected columns: {missing}")

    frame = frame.dropna(how="all").copy()
    frame.insert(0, "deposit_id", frame.apply(_stable_deposit_id, axis=1))
    frame["deposit_uri"] = (
        "https://example.org/mineraltwin/" + frame["deposit_id"].astype(str)
    )

    for column in frame.select_dtypes(include="object").columns:
        frame[column] = frame[column].map(clean_text)

    frame["Longitude"] = pd.to_numeric(frame["Longitude"], errors="coerce")
    frame["Latitude"] = pd.to_numeric(frame["Latitude"], errors="coerce")
    frame["valid_coordinates"] = (
        frame["Longitude"].between(-180, 180, inclusive="both")
        & frame["Latitude"].between(-90, 90, inclusive="both")
    )

    def collect_commodities(row: pd.Series) -> list[str]:
        values: set[str] = set()
        for column in COMMODITY_COLUMNS:
            if column in row.index:
                values.update(tokenize_commodities(row.get(column)))

        for commodity, column in ENDOWMENT_COLUMNS.items():
            if column in row.index and pd.notna(row.get(column)):
                values.add(commodity)
        return sorted(values)

    frame["commodity_codes"] = frame.apply(collect_commodities, axis=1)
    frame["commodity_codes_text"] = frame["commodity_codes"].map("|".join)

    for commodity in TARGET_COMMODITIES:
        frame[f"has_{commodity.lower()}"] = frame["commodity_codes"].map(
            lambda codes, c=commodity: c in codes
        )

    selected = BASE_COLUMNS + list(GRADE_COLUMNS.values()) + list(ENDOWMENT_COLUMNS.values())
    selected = ["deposit_id", "deposit_uri"] + _available_columns(frame, selected)
    selected += [
        "commodity_codes_text",
        "has_li",
        "has_cu",
        "has_ni",
        "valid_coordinates",
    ]

    return frame.loc[:, list(dict.fromkeys(selected))].copy()


def build_host_rock_table(raw_frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for _, row in raw_frame.iterrows():
        for index in range(1, 7):
            unit = clean_text(row.get(f"Host rock {index} - unit name"))
            stratno = clean_text(row.get(f"Host rock {index} - STRATNO"))
            lithology = clean_text(row.get(f"Host rock {index} - lithology"))
            age = clean_text(row.get(f"Host rock {index} - age"))
            if not any((unit, stratno, lithology, age)):
                continue
            records.append(
                {
                    "deposit_id": _stable_deposit_id(row),
                    "deposit": clean_text(row.get("Deposit")),
                    "host_rock_order": index,
                    "unit_name": unit,
                    "stratno": stratno,
                    "lithology": lithology,
                    "age": age,
                }
            )
    return pd.DataFrame.from_records(records)


def build_igneous_rock_table(raw_frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for _, row in raw_frame.iterrows():
        for index in range(1, 10):
            prefix = f"Associated igneous rock {index}"
            unit = clean_text(row.get(f"{prefix} - unit name"))
            stratno = clean_text(row.get(f"{prefix} - STRATNO"))
            lithology = clean_text(row.get(f"{prefix} - lithology"))
            age = clean_text(row.get(f"{prefix} - age"))
            timing = clean_text(row.get(f"{prefix} - timing relative to mineralisation"))
            if not any((unit, stratno, lithology, age, timing)):
                continue
            records.append(
                {
                    "deposit_id": _stable_deposit_id(row),
                    "deposit": clean_text(row.get("Deposit")),
                    "igneous_rock_order": index,
                    "unit_name": unit,
                    "stratno": stratno,
                    "lithology": lithology,
                    "age": age,
                    "timing_relative_to_mineralisation": timing,
                }
            )
    return pd.DataFrame.from_records(records)


def build_alteration_table(raw_frame: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "regional": "Regional alteration assemblages",
        "proximal": "Proximal alteration assemblages",
        "group": "Alteration assemblage group",
    }
    records: list[dict[str, Any]] = []
    for _, row in raw_frame.iterrows():
        for alteration_type, source_column in columns.items():
            value = clean_text(row.get(source_column))
            if not value:
                continue
            records.append(
                {
                    "deposit_id": _stable_deposit_id(row),
                    "deposit": clean_text(row.get("Deposit")),
                    "alteration_type": alteration_type,
                    "alteration_description": value,
                }
            )
    return pd.DataFrame.from_records(records)


def select_research_sample(
    clean_frame: pd.DataFrame,
    sample_size: int = SAMPLE_SIZE,
) -> pd.DataFrame:
    target_mask = clean_frame[["has_li", "has_cu", "has_ni"]].any(axis=1)
    candidates = clean_frame.loc[target_mask & clean_frame["valid_coordinates"]].copy()

    if candidates.empty:
        raise ValueError("No Li, Cu or Ni deposits with valid coordinates were found.")

    candidates["target_priority"] = (
        candidates["has_li"].astype(int) * 300
        + candidates["has_cu"].astype(int) * 200
        + candidates["has_ni"].astype(int) * 100
    )

    evidence_columns = [
        column
        for column in (
            "Principal deposit type",
            "Province",
            "Major/co-products",
            "Regional alteration assemblages",
            "Proximal alteration assemblages",
            "Source(s) of data - geology",
            "Comments",
        )
        if column in candidates.columns
    ]
    candidates["evidence_completeness"] = candidates[evidence_columns].notna().sum(axis=1)

    candidates = candidates.sort_values(
        ["target_priority", "evidence_completeness", "Deposit"],
        ascending=[False, False, True],
    )
    return candidates.head(sample_size).reset_index(drop=True)


def normalize_occurrence_geojson(
    input_path: Path = OCCURRENCES_GEOJSON,
) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8") as file:
        collection = json.load(file)

    if collection.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")

    normalized_features: list[dict[str, Any]] = []
    for index, feature in enumerate(collection.get("features", []), start=1):
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        properties = feature.get("properties") or {}
        name = clean_text(properties.get("name")) or f"Occurrence {index}"
        source_id = feature.get("id") or slugify(name)

        valid_point = (
            geometry.get("type") == "Point"
            and len(coordinates) >= 2
            and isinstance(coordinates[0], (int, float))
            and isinstance(coordinates[1], (int, float))
            and -180 <= coordinates[0] <= 180
            and -90 <= coordinates[1] <= 90
        )

        normalized_properties = {
            **properties,
            "occurrence_id": str(source_id),
            "occurrence_uri": (
                "https://example.org/mineraltwin/occurrence/" + slugify(source_id)
            ),
            "name": name,
            "valid_coordinates": valid_point,
            "source_dataset": "Geoscience Australia Mineral Occurrence sample",
        }
        normalized_features.append(
            {
                "type": "Feature",
                "id": source_id,
                "geometry": geometry,
                "properties": normalized_properties,
            }
        )

    return {
        "type": "FeatureCollection",
        "numberMatched": collection.get("numberMatched"),
        "features": normalized_features,
    }


def build_quality_report(
    clean_deposits: pd.DataFrame,
    sample: pd.DataFrame,
    host_rocks: pd.DataFrame,
    igneous_rocks: pd.DataFrame,
    alterations: pd.DataFrame,
    occurrence_collection: dict[str, Any],
) -> dict[str, Any]:
    duplicate_names = int(clean_deposits["Deposit"].duplicated(keep=False).sum())
    missing_coordinates = int((~clean_deposits["valid_coordinates"]).sum())

    return {
        "main_dataset": {
            "rows": int(len(clean_deposits)),
            "columns": int(len(clean_deposits.columns)),
            "duplicate_deposit_name_rows": duplicate_names,
            "invalid_or_missing_coordinate_rows": missing_coordinates,
            "lithium_rows": int(clean_deposits["has_li"].sum()),
            "copper_rows": int(clean_deposits["has_cu"].sum()),
            "nickel_rows": int(clean_deposits["has_ni"].sum()),
        },
        "research_sample": {
            "rows": int(len(sample)),
            "lithium_rows": int(sample["has_li"].sum()),
            "copper_rows": int(sample["has_cu"].sum()),
            "nickel_rows": int(sample["has_ni"].sum()),
        },
        "normalized_tables": {
            "host_rock_rows": int(len(host_rocks)),
            "associated_igneous_rock_rows": int(len(igneous_rocks)),
            "alteration_rows": int(len(alterations)),
            "occurrence_geojson_features": int(
                len(occurrence_collection.get("features", []))
            ),
        },
    }


def run_ingestion() -> PipelineOutputs:
    validate_input_files()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_frame = pd.read_excel(MAIN_WORKBOOK, sheet_name=MAIN_SHEET, engine="openpyxl")
    raw_frame.columns = [str(column).strip() for column in raw_frame.columns]
    raw_frame = raw_frame.dropna(how="all").copy()

    clean_deposits = load_main_deposits()
    sample = select_research_sample(clean_deposits)
    host_rocks = build_host_rock_table(raw_frame)
    igneous_rocks = build_igneous_rock_table(raw_frame)
    alterations = build_alteration_table(raw_frame)
    occurrences = normalize_occurrence_geojson()

    outputs = PipelineOutputs(
        deposits_clean=PROCESSED_DIR / "deposits_clean.csv",
        deposits_sample=PROCESSED_DIR / "deposits_research_sample_50.csv",
        host_rocks=PROCESSED_DIR / "host_rocks.csv",
        igneous_rocks=PROCESSED_DIR / "associated_igneous_rocks.csv",
        alterations=PROCESSED_DIR / "alterations.csv",
        occurrences_geojson=PROCESSED_DIR / "mineral_occurrences_normalized.geojson",
        quality_report=PROCESSED_DIR / "data_quality_report.json",
    )

    clean_deposits.to_csv(outputs.deposits_clean, index=False)
    sample.to_csv(outputs.deposits_sample, index=False)
    host_rocks.to_csv(outputs.host_rocks, index=False)
    igneous_rocks.to_csv(outputs.igneous_rocks, index=False)
    alterations.to_csv(outputs.alterations, index=False)

    with outputs.occurrences_geojson.open("w", encoding="utf-8") as file:
        json.dump(occurrences, file, indent=2, ensure_ascii=False)

    report = build_quality_report(
        clean_deposits,
        sample,
        host_rocks,
        igneous_rocks,
        alterations,
        occurrences,
    )
    with outputs.quality_report.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    return outputs


def load_reference_tables() -> dict[str, pd.DataFrame]:
    """Load the compact lookup tables used later by the ontology pipeline."""
    return {
        "deposit_classification": pd.read_excel(
            DEPOSIT_CLASSIFICATION,
            sheet_name="Deposit Classification",
            engine="openpyxl",
        ),
        "minerals": pd.read_excel(
            MINERAL_ABBREVIATIONS,
            sheet_name="Minerals",
            engine="openpyxl",
        ),
        "alteration_groups": pd.read_excel(
            MINERAL_ABBREVIATIONS,
            sheet_name="Alteration groups",
            engine="openpyxl",
        ),
        "tectonic_provinces": pd.read_excel(
            TECTONIC_PROVINCES,
            sheet_name="Sheet1",
            engine="openpyxl",
        ),
    }
