# Phase 2: RDF knowledge graph and SHACL validation

This phase converts the cleaned 50-deposit research sample into a provenance-aware RDF knowledge graph.

## Install the additional packages

```powershell
pip install -r requirements-semantic.txt
```

## Run in order

```powershell
python run_pipeline.py
python run_semantic_pipeline.py
python -m pytest -q
```

## Outputs

The semantic pipeline writes these files to `data/processed/knowledge_graph/`:

- `mineraltwin_kg.ttl`
- `mineraltwin_kg.jsonld`
- `semantic_summary.json`
- `validation_report.ttl`
- `validation_report.txt`
- `example_query_results.json`

## What this demonstrates

- OWL/RDF ontology design
- stable URIs for deposits and geological concepts
- GeoSPARQL-compatible WKT geometry
- commodity, province, host-rock, lithology and alteration relationships
- provenance using PROV-O
- SHACL data-quality rules
- competency questions written as SPARQL

The next phase will extract geological entities and claims from the downloaded PDF reports, attach confidence and provenance, and ground retrieval in both report passages and the RDF graph.
