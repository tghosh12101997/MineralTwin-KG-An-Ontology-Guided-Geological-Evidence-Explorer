from __future__ import annotations

import json
import sys

from src.semantic_model import (
    GRAPH_DIR,
    ONTOLOGY_PATH,
    SHAPES_PATH,
    build_knowledge_graph,
    run_example_queries,
    write_graph_outputs,
)
from src.validation import validate_graph


def main() -> None:
    graph = build_knowledge_graph()
    graph_turtle, graph_jsonld, semantic_summary = write_graph_outputs(graph)

    conforms, report_graph, report_text = validate_graph(
        graph,
        shapes_path=SHAPES_PATH,
        ontology_path=ONTOLOGY_PATH,
    )

    validation_turtle = GRAPH_DIR / "validation_report.ttl"
    validation_text = GRAPH_DIR / "validation_report.txt"
    query_results = GRAPH_DIR / "example_query_results.json"

    report_graph.serialize(destination=validation_turtle, format="turtle")
    validation_text.write_text(report_text, encoding="utf-8")
    query_results.write_text(
        json.dumps(run_example_queries(graph), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = json.loads(semantic_summary.read_text(encoding="utf-8"))

    print("\nMineralTwin-KG semantic pipeline completed.\n")
    print(f"Graph Turtle          -> {graph_turtle}")
    print(f"Graph JSON-LD         -> {graph_jsonld}")
    print(f"SHACL report Turtle   -> {validation_turtle}")
    print(f"SHACL report text     -> {validation_text}")
    print(f"Query results         -> {query_results}")
    print(f"Semantic summary      -> {semantic_summary}")
    print("\nGraph summary:")
    print(json.dumps(summary, indent=2))
    print(f"\nSHACL conforms: {conforms}")

    if not conforms:
        print("\nOpen validation_report.txt to inspect the violations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
