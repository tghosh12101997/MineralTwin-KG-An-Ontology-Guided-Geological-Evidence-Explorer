from __future__ import annotations

import json
import sys
from collections import Counter

from src.claim_graph import GRAPH_DIR, ONTOLOGY_PATH, add_report_claims, load_base_graph, write_phase3_graph
from src.domain_extraction import extract_corpus, write_extraction_outputs
from src.report_extraction import extract_reports, write_report_outputs
from src.retrieval import retrieve_evidence
from src.semantic_model import SHAPES_PATH, run_example_queries
from src.validation import validate_graph

DEMO_QUESTIONS = [
    "Which passages discuss lithium mineralization hosted by pegmatite?",
    "What geological structures control mineralization?",
    "Which alteration types are associated with mineralization?",
]


def main() -> None:
    documents, passages = extract_reports()
    documents_path, passages_path = write_report_outputs(documents, passages)

    entities, claims = extract_corpus(passages)
    entities_path, claims_path, review_path = write_extraction_outputs(entities, claims)

    graph = load_base_graph()
    graph = add_report_claims(graph, documents, passages, entities, claims)
    graph_turtle, graph_jsonld = write_phase3_graph(graph)

    conforms, report_graph, report_text = validate_graph(
        graph,
        shapes_path=SHAPES_PATH,
        ontology_path=ONTOLOGY_PATH,
    )
    validation_turtle = GRAPH_DIR / "validation_phase3_report.ttl"
    validation_text = GRAPH_DIR / "validation_phase3_report.txt"
    report_graph.serialize(destination=validation_turtle, format="turtle")
    validation_text.write_text(report_text, encoding="utf-8")

    phase3_queries = GRAPH_DIR / "phase3_query_results.json"
    phase3_queries.write_text(
        json.dumps(run_example_queries(graph), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    retrieval_path = GRAPH_DIR / "retrieval_demo.json"
    retrieval_path.write_text(
        json.dumps(
            {question: retrieve_evidence(question, passages, claims, top_k=5) for question in DEMO_QUESTIONS},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = {
        "documents": len(documents),
        "pages": sum(item.page_count for item in documents),
        "pages_with_text": sum(item.pages_with_text for item in documents),
        "passages": len(passages),
        "entities": len(entities),
        "entity_types": dict(Counter(item.entity_type for item in entities)),
        "claims": len(claims),
        "claim_predicates": dict(Counter(item.predicate for item in claims)),
        "claims_needing_review": sum(item.review_status == "needs-review" for item in claims),
        "graph_triples": len(graph),
        "shacl_conforms": conforms,
    }
    summary_path = GRAPH_DIR / "phase3_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nMineralTwin-KG Phase 3 completed.\n")
    print(f"Documents              -> {documents_path}")
    print(f"Passages               -> {passages_path}")
    print(f"Entities               -> {entities_path}")
    print(f"Claims                 -> {claims_path}")
    print(f"Human review queue     -> {review_path}")
    print(f"Phase 3 graph Turtle   -> {graph_turtle}")
    print(f"Phase 3 graph JSON-LD  -> {graph_jsonld}")
    print(f"Validation report      -> {validation_text}")
    print(f"Retrieval demonstration-> {retrieval_path}")
    print(f"Phase 3 summary        -> {summary_path}\n")
    print(json.dumps(summary, indent=2))

    if not conforms:
        print("\nSHACL validation failed. Open validation_phase3_report.txt.")
        sys.exit(1)
    if not claims:
        print("\nNo claims were extracted. Check that the PDFs contain selectable text and geological prose.")
        sys.exit(2)


if __name__ == "__main__":
    main()
