# MineralTwin-KG Phase 3

Phase 3 turns geological PDF reports into provenance-aware, confidence-scored RDF claims.

## Before running

Place both geological PDF files directly inside:

```text
data/reports/
```

The filenames may be anything ending in `.pdf`.

## Install

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-phase3.txt
```

## Run

Run the previous phases first if needed:

```powershell
python run_pipeline.py
python run_semantic_pipeline.py
```

Then run:

```powershell
python run_phase3.py
```

## Outputs

```text
data/processed/reports/documents.json
data/processed/reports/passages.jsonl
data/processed/reports/extracted_entities.csv
data/processed/reports/extracted_claims.csv
data/processed/reports/review_queue.csv

data/processed/knowledge_graph/mineraltwin_kg_phase3.ttl
data/processed/knowledge_graph/mineraltwin_kg_phase3.jsonld
data/processed/knowledge_graph/validation_phase3_report.txt
data/processed/knowledge_graph/retrieval_demo.json
data/processed/knowledge_graph/phase3_summary.json
```

## Ask a question against the evidence index

```powershell
python ask_evidence.py "Which passages discuss lithium mineralisation hosted by pegmatite?"
```

This is retrieval, not free-form generation. Each result includes the PDF filename, page number, passage, score and any structured claims extracted from that passage.

## Research integrity

The pipeline does not assert extracted relations directly as unquestioned facts. It stores each relation as an `mt:ExtractedClaim` with source text, page provenance, extraction method, confidence and review status. Claims below 0.85 are placed in `review_queue.csv` for human inspection.

## PDF note

`pypdf` extracts selectable text. If a report produces very few passages, open the PDF and check whether its text can be selected. Scanned-image PDFs require OCR and should not be used for this rapid prototype.
