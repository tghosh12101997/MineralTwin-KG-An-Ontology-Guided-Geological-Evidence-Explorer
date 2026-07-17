from rdflib import RDF
from rdflib.namespace import GEO

from src.semantic_model import MT, build_knowledge_graph, summarize_graph
from src.validation import validate_graph
from src.semantic_model import ONTOLOGY_PATH, SHAPES_PATH


def test_graph_contains_expected_core_entities():
    graph = build_knowledge_graph()
    summary = summarize_graph(graph)

    assert summary["mineral_deposits"] == 50
    assert summary["commodities"] >= 3
    assert summary["geometries"] == 50
    assert any(graph.subjects(RDF.type, MT.GeologicalUnit))
    assert any(graph.subjects(RDF.type, GEO.Geometry))


def test_graph_conforms_to_shacl():
    graph = build_knowledge_graph()
    conforms, _, report_text = validate_graph(
        graph,
        shapes_path=SHAPES_PATH,
        ontology_path=ONTOLOGY_PATH,
    )
    assert conforms, report_text
