from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS

from src.dashboard_data import (
    DashboardPaths,
    filter_deposits,
    graph_neighborhood,
    retrieve_evidence_from_files,
)


def test_filter_deposits_by_commodity() -> None:
    frame = pd.DataFrame(
        [
            {"Deposit": "Alpha", "commodity_codes_text": "Li|Ta", "State": "WA"},
            {"Deposit": "Beta", "commodity_codes_text": "Cu", "State": "SA"},
        ]
    )
    result = filter_deposits(frame, commodities=["Li"])
    assert result["Deposit"].tolist() == ["Alpha"]


def test_retrieval_returns_attached_claims() -> None:
    passages = [
        {"passage_id": "p1", "text": "Lithium mineralisation is hosted by pegmatite."},
        {"passage_id": "p2", "text": "A regional fault crosses the area."},
    ]
    claims = pd.DataFrame(
        [{"passage_id": "p1", "predicate": "hostedBy", "confidence": 0.9}]
    )
    results = retrieve_evidence_from_files("lithium pegmatite", passages, claims, top_k=1)
    assert results[0]["passage"]["passage_id"] == "p1"
    assert results[0]["claims"][0]["predicate"] == "hostedBy"


def test_graph_neighborhood() -> None:
    graph = Graph()
    ex = Namespace("https://example.org/")
    graph.add((ex.deposit, RDF.type, ex.MineralDeposit))
    graph.add((ex.deposit, RDFS.label, Literal("Test Deposit")))
    graph.add((ex.deposit, ex.containsCommodity, ex.lithium))
    graph.add((ex.lithium, RDFS.label, Literal("Lithium")))
    result = graph_neighborhood(graph, str(ex.deposit))
    assert not result.empty
    assert "Lithium" in result["target"].tolist()


def test_paths_are_project_relative(tmp_path: Path) -> None:
    paths = DashboardPaths.from_project_root(tmp_path)
    assert paths.deposits == tmp_path / "data" / "processed" / "deposits_clean.csv"
