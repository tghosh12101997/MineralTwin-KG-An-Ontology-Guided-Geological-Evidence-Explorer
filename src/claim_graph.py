from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from rdflib import DCTERMS, Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD
from rdflib.namespace import PROV

from .config import PROCESSED_DIR, PROJECT_ROOT
from .domain_extraction import EntityMention, ExtractedClaimRecord
from .report_extraction import DocumentRecord, PassageRecord

MT = Namespace("https://w3id.org/mineraltwin/ontology/")
RES = Namespace("https://w3id.org/mineraltwin/resource/")
ONTOLOGY_PATH = PROJECT_ROOT / "ontology" / "mineraltwin.ttl"
BASE_GRAPH_PATH = PROCESSED_DIR / "knowledge_graph" / "mineraltwin_kg.ttl"
GRAPH_DIR = PROCESSED_DIR / "knowledge_graph"

ENTITY_CLASSES = {
    "LITHOLOGY": MT.Lithology,
    "STRUCTURE": MT.GeologicalStructure,
    "ALTERATION": MT.AlterationAssemblage,
    "MINERAL": MT.Mineral,
    "COMMODITY": MT.Commodity,
    "MINERALIZATION": MT.Mineralization,
    "GEOCHEMICAL_VALUE": MT.GeochemicalObservation,
}

PREDICATES = {
    "hostedBy": MT.hostedBy,
    "associatedWithAlteration": MT.associatedWithAlteration,
    "controlledByStructure": MT.controlledByStructure,
    "containsMineral": MT.containsMineral,
    "hasGeochemicalEvidence": MT.hasGeochemicalEvidence,
}

COMMODITY_CODES = {
    "Li": "Lithium", "Ni": "Nickel", "Cu": "Copper", "Co": "Cobalt",
    "Au": "Gold", "Ta": "Tantalum", "Sn": "Tin", "Ag": "Silver",
    "Zn": "Zinc", "Pb": "Lead", "Mo": "Molybdenum", "W": "Tungsten",
    "U": "Uranium", "Be": "Beryllium", "REE": "Rare earth elements",
}


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "unknown"


def _stable_uri(kind: str, label: str) -> URIRef:
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:12]
    return RES[f"entity/{kind}/{_slugify(label)[:60]}-{digest}"]


def _entity_uri(entity: EntityMention) -> URIRef:
    if entity.entity_type == "DEPOSIT" and entity.entity_id.startswith("deposit:"):
        return RES[f"deposit/{entity.entity_id.split(':', 1)[1]}"]
    if entity.entity_type == "COMMODITY" and entity.entity_id.startswith("commodity:"):
        code = entity.entity_id.split(":", 1)[1]
        return RES[f"commodity/{_slugify(code)}"]
    return _stable_uri(entity.entity_type.lower(), entity.normalized_text)


def load_base_graph() -> Graph:
    graph = Graph()
    graph.bind("mt", MT)
    graph.bind("res", RES)
    graph.bind("prov", PROV)
    if BASE_GRAPH_PATH.exists():
        graph.parse(BASE_GRAPH_PATH, format="turtle")
    else:
        from .semantic_model import build_knowledge_graph
        graph = build_knowledge_graph()
    graph.parse(ONTOLOGY_PATH, format="turtle")
    return graph


def add_report_claims(
    graph: Graph,
    documents: list[DocumentRecord],
    passages: list[PassageRecord],
    entities: list[EntityMention],
    claims: list[ExtractedClaimRecord],
) -> Graph:
    document_uri_by_id: dict[str, URIRef] = {}
    passage_uri_by_id: dict[str, URIRef] = {}
    entity_uri_by_id: dict[tuple[str, str], URIRef] = {}

    activity_uri = RES["activity/rule-based-geological-extraction-v1"]
    graph.add((activity_uri, RDF.type, MT.ExtractionActivity))
    graph.add((activity_uri, RDFS.label, Literal("Rule-based geological entity and relation extraction v1")))

    for document in documents:
        uri = RES[f"document/{document.document_id}"]
        document_uri_by_id[document.document_id] = uri
        graph.add((uri, RDF.type, MT.EvidenceDocument))
        graph.add((uri, RDF.type, MT.EvidenceSource))
        graph.add((uri, RDFS.label, Literal(document.title)))
        graph.add((uri, MT.documentFilename, Literal(document.filename)))
        graph.add((uri, DCTERMS.identifier, Literal(document.document_id)))

    for passage in passages:
        uri = RES[f"passage/{passage.passage_id}"]
        passage_uri_by_id[passage.passage_id] = uri
        graph.add((uri, RDF.type, MT.ReportPassage))
        graph.add((uri, RDF.type, MT.EvidenceSource))
        graph.add((uri, MT.pageNumber, Literal(passage.page_number, datatype=XSD.integer)))
        graph.add((uri, MT.passageText, Literal(passage.text)))
        document_uri = document_uri_by_id[passage.document_id]
        graph.add((uri, PROV.wasDerivedFrom, document_uri))

    for entity in entities:
        uri = _entity_uri(entity)
        entity_uri_by_id[(entity.passage_id, entity.entity_id)] = uri
        passage_uri = passage_uri_by_id[entity.passage_id]
        if entity.entity_type == "DEPOSIT":
            graph.add((uri, RDF.type, MT.MineralDeposit))
            if not list(graph.objects(uri, RDFS.label)):
                graph.add((uri, RDFS.label, Literal(entity.text)))
        else:
            class_uri = ENTITY_CLASSES.get(entity.entity_type, MT.GeologicalEntity)
            graph.add((uri, RDF.type, class_uri))
            graph.add((uri, RDFS.label, Literal(entity.text)))
            graph.add((uri, MT.entityType, Literal(entity.entity_type)))
            if entity.entity_type == "COMMODITY":
                code = entity.entity_id.split(":", 1)[1]
                graph.set((uri, MT.commodityCode, Literal(code)))
                graph.set((uri, RDFS.label, Literal(COMMODITY_CODES.get(code, entity.text))))
            if entity.entity_type == "GEOCHEMICAL_VALUE":
                graph.add((uri, MT.assayText, Literal(entity.text)))
        graph.add((passage_uri, MT.mentionsEntity, uri))

    entity_lookup: dict[tuple[str, str], EntityMention] = {
        (item.passage_id, item.entity_id): item for item in entities
    }
    for claim in claims:
        claim_uri = RES[f"claim/{claim.claim_id}"]
        subject_mention = entity_lookup[(claim.passage_id, claim.subject_id)]
        object_mention = entity_lookup[(claim.passage_id, claim.object_id)]
        subject_uri = entity_uri_by_id[(claim.passage_id, claim.subject_id)]
        object_uri = entity_uri_by_id[(claim.passage_id, claim.object_id)]
        predicate_uri = PREDICATES[claim.predicate]
        passage_uri = passage_uri_by_id[claim.passage_id]

        graph.add((claim_uri, RDF.type, MT.ExtractedClaim))
        graph.add((claim_uri, MT.claimSubject, subject_uri))
        graph.add((claim_uri, MT.claimPredicate, predicate_uri))
        graph.add((claim_uri, MT.claimObject, object_uri))
        graph.add((claim_uri, MT.confidenceScore, Literal(str(claim.confidence), datatype=XSD.decimal)))
        graph.add((claim_uri, MT.sourceText, Literal(claim.source_text)))
        graph.add((claim_uri, MT.extractionMethod, Literal(claim.extraction_method)))
        graph.add((claim_uri, MT.reviewStatus, Literal(claim.review_status)))
        graph.add((claim_uri, MT.supportedByPassage, passage_uri))
        graph.add((claim_uri, PROV.wasDerivedFrom, passage_uri))
        graph.add((claim_uri, PROV.wasGeneratedBy, activity_uri))

        # Keep uncertain extractions reified instead of asserting them as factual triples.
        graph.add((subject_uri, MT.entityType, Literal(subject_mention.entity_type)))
        graph.add((object_uri, MT.entityType, Literal(object_mention.entity_type)))

    return graph


def write_phase3_graph(graph: Graph) -> tuple[Path, Path]:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    turtle_path = GRAPH_DIR / "mineraltwin_kg_phase3.ttl"
    jsonld_path = GRAPH_DIR / "mineraltwin_kg_phase3.jsonld"
    graph.serialize(destination=turtle_path, format="turtle")
    graph.serialize(destination=jsonld_path, format="json-ld", indent=2)
    return turtle_path, jsonld_path
