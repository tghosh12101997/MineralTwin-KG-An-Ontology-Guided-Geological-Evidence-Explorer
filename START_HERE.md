# MineralTwin-KG: Phase 1

This starter runs the first project milestone: validating, cleaning and sampling the geological datasets.

## 1. Merge these files into your existing project

Copy the contents of this starter folder into the root of `MINERALTWIN-KG`.

Your data files must remain here:

```text
data/raw/australian_mineral_deposits.xlsx
data/raw/commodity_endowment_calculations.xlsx
data/raw/deposit_classification.xlsx
data/raw/mineral_abbreviations.xlsx
data/raw/tectonic_provinces.xlsx
data/raw/mineral_occurrences_sample.geojson
```

Keep the PDFs in `data/reports/` and the GemPy CSVs in `data/gempy/`.

## 2. Create the environment

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Run the pipeline

```bash
python run_pipeline.py
```

Expected outputs:

```text
data/processed/deposits_clean.csv
data/processed/deposits_research_sample_50.csv
data/processed/host_rocks.csv
data/processed/associated_igneous_rocks.csv
data/processed/alterations.csv
data/processed/mineral_occurrences_normalized.geojson
data/processed/data_quality_report.json
```

## 4. Run the small tests

```bash
python -m pytest -q
```

## What comes next

Phase 2 converts the cleaned sample to RDF, defines the mineral-system ontology in Turtle, and validates the graph with SHACL.
