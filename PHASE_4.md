# MineralTwin-KG Phase 4: Streamlit research dashboard

Phase 4 turns the pipeline outputs into a usable research interface. It does not replace the data, ontology or NLP pipelines; it reads their generated files.

## Pages

1. **Overview**: project metrics, architecture and pipeline readiness.
2. **Deposit Explorer**: filters, Australian map, deposit records, host rocks, alteration and igneous rocks.
3. **Evidence Search**: TF-IDF retrieval over PDF passages with attached confidence-scored claims.
4. **Knowledge Graph**: RDF type statistics, resource neighborhoods and read-only SPARQL SELECT queries.
5. **Claim Review**: human decisions for uncertain claims, saved to `data/processed/reports/review_decisions.csv`.
6. **3D Model Inputs**: interactive inspection of GemPy surface points and orientations.
7. **Methods**: research question, modelling choices and limitations.

## Add the files

Copy everything inside this update folder into the root of the existing `MINERALTWIN-KG` repository. The update adds:

```text
MINERALTWIN-KG/
├── dashboard.py
├── requirements-dashboard.txt
├── .streamlit/
│   └── config.toml
├── src/
│   └── dashboard_data.py
└── tests/
    └── test_dashboard_data.py
```

Existing source files are not replaced.

## Required execution order

Run the pipelines once before starting the dashboard:

```powershell
python run_pipeline.py
python run_semantic_pipeline.py
python run_phase3.py
```

Then install the dashboard dependencies:

```powershell
pip install -r requirements-dashboard.txt
```

Start the interface:

```powershell
streamlit run dashboard.py
```

The local dashboard normally opens automatically in a browser. If it does not, open the local address displayed in the terminal.

## Tests

```powershell
python -m pytest -q
```

The dashboard adds four tests to the existing test suite.

## What is not yet included

The 3D page currently visualizes the GemPy input observations. It does not yet run the full implicit interpolation. That should be Phase 5 after the dashboard and Phase 3 extraction results have been checked.
