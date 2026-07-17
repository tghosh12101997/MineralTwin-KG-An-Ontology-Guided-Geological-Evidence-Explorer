from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from rdflib import DCTERMS, Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD
from rdflib.namespace import GEO, OWL, PROV

from .config import PROCESSED_DIR, PROJECT_ROOT

ONTOLOGY_DIR = PROJECT_ROOT / "ontology"
QUERY_DIR = PROJECT_ROOT / "queries"
GRAPH_DIR = PROCESSED_DIR / "knowledge_graph"

ONTOLOGY_PATH = ONTOLOGY_DIR / "mineraltwin.ttl"
SHAPES_PATH = ONTOLOGY_DIR / "shapes.ttl"

DEPOSIT_SAMPLE_PATH = PROCESSED_DIR / "deposits_research_sample_50.csv"
HOST_ROCKS_PATH = PROCESSED_DIR / "host_rocks.csv"
ALTERATIONS_PATH = PROCESSED_DIR / "alterations.csv"

MT = Namespace("https://w3id.org/mineraltwin/ontology/")
RES = Namespace("https://w3id.org/mineraltwin/resource/")

COMMODITY_LABELS = {
    "Ag": "Silver",
    "Au": "Gold",
    "Be": "Beryllium",
    "Bi": "Bismuth",
    "Co": "Cobalt",
    "Cu": "Copper",
    "F": "Fluorine",
    "Fe": "Iron",
    "Li": "Lithium",
    "Mo": "Molybdenum",
    "Ni": "Nickel",
    "Pb": "Lead",
    "REE": "Rare earth elements",
    "Sn": "Tin",
    "Ta": "Tantalum",
    "U": "Uranium",
    "W": "Tungsten",
    "Zn": "Zinc",
}

SOURCE_COLUMNS = {
    "location": "Source(s) of data - location",
    "geology": "Source(s) of data - geology",
    "age": "Source(s) of data - age",
    "resources": "Source(s) of data - resources/endowment",
}

NUMERIC_PROPERTIES = {
    "Li2O (%)": MT.gradeLi2OPercent,
    "Cu (%)": MT.gradeCopperPercent,
    "Ni (%)": MT.gradeNickelPercent,
    "Li (Mt)": MT.endowmentLithiumMt,
    "Cu (Mt)": MT.endowmentCopperMt,
    "Ni (Mt)": MT.endowmentNickelMt,
}


@dataclass(frozen=True)
class SemanticOutputs:
    graph_turtle: Path
    graph_jsonld: Path
    validation_report_turtle: Path
    validation_report_text: Path
    semantic_summary: Path
    query_results: Path


def slugify(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def clean_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def decimal_literal(value: object) -> Literal | None:
    if value is None or pd.isna(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return Literal(str(numeric), datatype=XSD.decimal)


def _stable_text_uri(kind: str, text: str) -> URIRef:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return RES[f"{kind}/{slugify(text)[:70]}-{digest}"]


def _add_labelled_resource(
    graph: Graph,
    uri: URIRef,
    class_uri: URIRef,
    label: str,
) -> URIRef:
    graph.add((uri, RDF.type, class_uri))
    graph.add((uri, RDFS.label, Literal(label)))
    return uri


def _bind_namespaces(graph: Graph) -> None:
    graph.bind("mt", MT)
    graph.bind("res", RES)
    graph.bind("geo", GEO)
    graph.bind("prov", PROV)
    graph.bind("dcterms", DCTERMS)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)


def _require_processed_files(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Run `python run_pipeline.py` first. Missing processed files:\n  - "
            + "\n  - ".join(missing)
        )


def _add_dimension(
    graph: Graph,
    deposit_uri: URIRef,
    value: object,
    kind: str,
    class_uri: URIRef,
    predicate: URIRef,
) -> None:
    label = clean_text(value)
    if not label:
        return
    resource_uri = _stable_text_uri(kind, label)
    _add_labelled_resource(graph, resource_uri, class_uri, label)
    graph.add((deposit_uri, predicate, resource_uri))


def _add_evidence_source(
    graph: Graph,
    deposit_uri: URIRef,
    source_kind: str,
    source_text: str,
) -> None:
    source_uri = _stable_text_uri(f"source/{source_kind}", source_text)
    _add_labelled_resource(graph, source_uri, MT.EvidenceSource, source_text)
    graph.add((source_uri, DCTERMS.type, Literal(source_kind)))
    graph.add((deposit_uri, PROV.wasDerivedFrom, source_uri))


def build_knowledge_graph() -> Graph:
    _require_processed_files(
        [DEPOSIT_SAMPLE_PATH, HOST_ROCKS_PATH, ALTERATIONS_PATH, ONTOLOGY_PATH]
    )

    deposits = pd.read_csv(DEPOSIT_SAMPLE_PATH)
    host_rocks = pd.read_csv(HOST_ROCKS_PATH)
    alterations = pd.read_csv(ALTERATIONS_PATH)

    sample_ids = set(deposits["deposit_id"].astype(str))
    host_rocks = host_rocks[host_rocks["deposit_id"].astype(str).isin(sample_ids)]
    alterations = alterations[alterations["deposit_id"].astype(str).isin(sample_ids)]

    graph = Graph()
    _bind_namespaces(graph)
    graph.parse(ONTOLOGY_PATH, format="turtle")

    dataset_uri = RES["dataset/australian-mineral-deposits-2024"]
    _add_labelled_resource(
        graph,
        dataset_uri,
        MT.EvidenceSource,
        "Australian mineral deposits compilation (2024)",
    )
    graph.add((dataset_uri, DCTERMS.type, Literal("dataset")))

    for _, row in deposits.iterrows():
        deposit_id = str(row["deposit_id"])
        deposit_uri = RES[f"deposit/{deposit_id}"]
        label = clean_text(row.get("Deposit")) or deposit_id

        graph.add((deposit_uri, RDF.type, MT.MineralDeposit))
        graph.add((deposit_uri, RDFS.label, Literal(label)))
        graph.add((deposit_uri, MT.sourceRecordId, Literal(deposit_id)))
        graph.add((deposit_uri, PROV.wasDerivedFrom, dataset_uri))

        longitude = float(row["Longitude"])
        latitude = float(row["Latitude"])
        geometry_uri = RES[f"geometry/{deposit_id}"]
        graph.add((geometry_uri, RDF.type, GEO.Geometry))
        graph.add(
            (
                geometry_uri,
                GEO.asWKT,
                Literal(
                    f"POINT ({longitude:.8f} {latitude:.8f})",
                    datatype=GEO.wktLiteral,
                ),
            )
        )
        graph.add((deposit_uri, GEO.hasGeometry, geometry_uri))

        _add_dimension(
            graph,
            deposit_uri,
            row.get("Principal deposit environment"),
            "environment",
            MT.DepositEnvironment,
            MT.hasPrincipalEnvironment,
        )
        _add_dimension(
            graph,
            deposit_uri,
            row.get("Principal deposit group"),
            "deposit-group",
            MT.DepositGroup,
            MT.hasPrincipalGroup,
        )
        _add_dimension(
            graph,
            deposit_uri,
            row.get("Principal deposit type"),
            "deposit-type",
            MT.DepositType,
            MT.hasDepositType,
        )
        _add_dimension(
            graph,
            deposit_uri,
            row.get("Province"),
            "province",
            MT.Province,
            MT.locatedInProvince,
        )
        _add_dimension(
            graph,
            deposit_uri,
            row.get("District"),
            "district",
            MT.District,
            MT.locatedInDistrict,
        )
        _add_dimension(
            graph,
            deposit_uri,
            row.get("State"),
            "state",
            MT.StateOrTerritory,
            MT.locatedInState,
        )

        codes = clean_text(row.get("commodity_codes_text"))
        for code in sorted(set(codes.split("|"))) if codes else []:
            code = code.strip()
            if not code:
                continue
            commodity_uri = RES[f"commodity/{slugify(code)}"]
            _add_labelled_resource(
                graph,
                commodity_uri,
                MT.Commodity,
                COMMODITY_LABELS.get(code, code),
            )
            graph.set((commodity_uri, MT.commodityCode, Literal(code)))
            graph.add((deposit_uri, MT.containsCommodity, commodity_uri))

        for column, predicate in NUMERIC_PROPERTIES.items():
            literal = decimal_literal(row.get(column))
            if literal is not None:
                graph.add((deposit_uri, predicate, literal))

        comment = clean_text(row.get("Comments"))
        if comment:
            graph.add((deposit_uri, RDFS.comment, Literal(comment)))

        for source_kind, column in SOURCE_COLUMNS.items():
            source_text = clean_text(row.get(column))
            if source_text:
                _add_evidence_source(graph, deposit_uri, source_kind, source_text)

    for _, row in host_rocks.iterrows():
        deposit_id = str(row["deposit_id"])
        deposit_uri = RES[f"deposit/{deposit_id}"]
        order = int(row["host_rock_order"])
        unit_name = clean_text(row.get("unit_name"))
        lithology = clean_text(row.get("lithology"))
        age = clean_text(row.get("age"))

        host_uri = RES[f"host-rock/{deposit_id}/{order}"]
        graph.add((host_uri, RDF.type, MT.GeologicalUnit))
        graph.add((host_uri, MT.hostRockOrder, Literal(order, datatype=XSD.integer)))
        if unit_name:
            graph.add((host_uri, RDFS.label, Literal(unit_name)))
        if age:
            graph.add((host_uri, MT.geologicalAgeText, Literal(age)))
        if lithology:
            lithology_uri = _stable_text_uri("lithology", lithology)
            _add_labelled_resource(graph, lithology_uri, MT.Lithology, lithology)
            graph.add((host_uri, MT.hasLithology, lithology_uri))
        graph.add((deposit_uri, MT.hasHostRock, host_uri))

    for _, row in alterations.iterrows():
        deposit_id = str(row["deposit_id"])
        description = clean_text(row.get("alteration_description"))
        scope = clean_text(row.get("alteration_type"))
        if not description:
            continue
        deposit_uri = RES[f"deposit/{deposit_id}"]
        alteration_uri = _stable_text_uri(
            f"alteration/{deposit_id}/{scope or 'unspecified'}", description
        )
        _add_labelled_resource(
            graph, alteration_uri, MT.AlterationAssemblage, description
        )
        if scope:
            graph.add((alteration_uri, MT.alterationScope, Literal(scope)))
        graph.add((deposit_uri, MT.hasAlteration, alteration_uri))

    return graph


def summarize_graph(graph: Graph) -> dict[str, int]:
    def count(class_uri: URIRef) -> int:
        return len(set(graph.subjects(RDF.type, class_uri)))

    return {
        "triples": len(graph),
        "mineral_deposits": count(MT.MineralDeposit),
        "commodities": count(MT.Commodity),
        "geological_units": count(MT.GeologicalUnit),
        "lithologies": count(MT.Lithology),
        "alteration_assemblages": count(MT.AlterationAssemblage),
        "evidence_sources": count(MT.EvidenceSource),
        "geometries": count(GEO.Geometry),
    }


def run_example_queries(graph: Graph) -> dict[str, list[dict[str, str]]]:
    results: dict[str, list[dict[str, str]]] = {}
    for query_path in sorted(QUERY_DIR.glob("*.rq")):
        rows: list[dict[str, str]] = []
        result = graph.query(query_path.read_text(encoding="utf-8"))
        for row in result:
            rows.append(
                {
                    str(variable): str(value) if value is not None else ""
                    for variable, value in zip(result.vars, row)
                }
            )
        results[query_path.name] = rows
    return results


def write_graph_outputs(graph: Graph) -> tuple[Path, Path, Path]:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    turtle_path = GRAPH_DIR / "mineraltwin_kg.ttl"
    jsonld_path = GRAPH_DIR / "mineraltwin_kg.jsonld"
    summary_path = GRAPH_DIR / "semantic_summary.json"

    graph.serialize(destination=turtle_path, format="turtle")
    graph.serialize(destination=jsonld_path, format="json-ld", indent=2)
    summary_path.write_text(
        json.dumps(summarize_graph(graph), indent=2), encoding="utf-8"
    )
    return turtle_path, jsonld_path, summary_path
