from __future__ import annotations

from pathlib import Path

from rdflib import BNode, Graph, Literal, RDF, URIRef
from rdflib.namespace import GEO, PROV, RDFS, SH

MT = URIRef("https://w3id.org/mineraltwin/ontology/")
MT_NS = "https://w3id.org/mineraltwin/ontology/"


def _fallback_validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Small dependency-free fallback used only when pySHACL is unavailable.

    The project still ships the real SHACL shapes. Installing pyshacl activates
    full SHACL validation automatically.
    """
    report = Graph()
    report.bind("sh", SH)
    report_node = BNode()
    report.add((report_node, RDF.type, SH.ValidationReport))

    violations: list[tuple[URIRef, str, URIRef | None]] = []
    deposit_class = URIRef(MT_NS + "MineralDeposit")
    commodity_property = URIRef(MT_NS + "containsCommodity")
    evidence_class = URIRef(MT_NS + "EvidenceSource")

    for deposit in set(data_graph.subjects(RDF.type, deposit_class)):
        labels = list(data_graph.objects(deposit, RDFS.label))
        geometries = list(data_graph.objects(deposit, GEO.hasGeometry))
        commodities = list(data_graph.objects(deposit, commodity_property))
        sources = list(data_graph.objects(deposit, PROV.wasDerivedFrom))

        if len(labels) != 1 or not str(labels[0]).strip():
            violations.append((deposit, "Deposit requires exactly one non-empty label.", RDFS.label))
        if len(geometries) != 1:
            violations.append((deposit, "Deposit requires exactly one geometry.", GEO.hasGeometry))
        else:
            wkt_values = list(data_graph.objects(geometries[0], GEO.asWKT))
            if len(wkt_values) != 1 or not str(wkt_values[0]).startswith("POINT"):
                violations.append((geometries[0], "Geometry requires one POINT WKT literal.", GEO.asWKT))
        if not commodities:
            violations.append((deposit, "Deposit requires at least one commodity.", commodity_property))
        valid_sources = [
            source
            for source in sources
            if (source, RDF.type, evidence_class) in data_graph
        ]
        if not valid_sources:
            violations.append((deposit, "Deposit requires at least one evidence source.", PROV.wasDerivedFrom))

    conforms = not violations
    report.add((report_node, SH.conforms, Literal(conforms)))

    lines = ["Validation Report", f"Conforms: {conforms}"]
    for focus, message, path in violations:
        result = BNode()
        report.add((report_node, SH.result, result))
        report.add((result, RDF.type, SH.ValidationResult))
        report.add((result, SH.resultSeverity, SH.Violation))
        report.add((result, SH.focusNode, focus))
        report.add((result, SH.resultMessage, Literal(message)))
        if path is not None:
            report.add((result, SH.resultPath, path))
        lines.append(f"Violation: {focus} | {message}")

    if conforms:
        lines.append("All core MineralTwin-KG constraints passed.")
    lines.append("Validator: built-in fallback (install pyshacl for full SHACL execution).")
    return conforms, report, "\n".join(lines)


def validate_graph(
    data_graph: Graph,
    shapes_path: Path,
    ontology_path: Path,
) -> tuple[bool, Graph, str]:
    try:
        from pyshacl import validate
    except ImportError:
        return _fallback_validate(data_graph)

    shapes_graph = Graph().parse(shapes_path, format="turtle")
    ontology_graph = Graph().parse(ontology_path, format="turtle")

    conforms, report_graph, report_text = validate(
        data_graph=data_graph,
        shacl_graph=shapes_graph,
        ont_graph=ontology_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
        meta_shacl=True,
        advanced=True,
    )
    return bool(conforms), report_graph, str(report_text)
