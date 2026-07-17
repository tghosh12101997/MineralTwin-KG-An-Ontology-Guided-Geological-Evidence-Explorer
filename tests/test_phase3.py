from rdflib import RDF

from src.claim_graph import MT, add_report_claims
from src.domain_extraction import extract_claims_from_passage, extract_entities_from_text
from src.report_extraction import DocumentRecord, PassageRecord, split_page_into_passages
from src.retrieval import retrieve_evidence


def sample_passage(text: str) -> PassageRecord:
    return PassageRecord(
        passage_id="passage-test",
        document_id="doc-test",
        filename="test.pdf",
        page_number=1,
        passage_index=1,
        text=text,
    )


def test_passage_split():
    text = "Lithium mineralisation is hosted within pegmatite.\n\nMuscovite alteration is associated with the ore zone."
    passages = split_page_into_passages(text, min_chars=20)
    assert len(passages) == 2


def test_extract_explicit_host_and_alteration_claims():
    passage = sample_passage(
        "Lithium mineralisation is hosted within pegmatite and is associated with muscovite alteration."
    )
    entities = extract_entities_from_text(passage, deposit_terms={})
    claims = extract_claims_from_passage(passage, entities)
    predicates = {claim.predicate for claim in claims}
    assert "hostedBy" in predicates
    assert "associatedWithAlteration" in predicates


def test_claim_graph_retains_reified_claim():
    passage = sample_passage("Lithium mineralisation is hosted within pegmatite.")
    entities = extract_entities_from_text(passage, deposit_terms={})
    claims = extract_claims_from_passage(passage, entities)
    document = DocumentRecord("doc-test", "test.pdf", "Test report", 1, 1)

    from rdflib import Graph
    graph = add_report_claims(Graph(), [document], [passage], entities, claims)
    assert len(set(graph.subjects(RDF.type, MT.ExtractedClaim))) == 1


def test_retrieval_prefers_relevant_passage():
    relevant = sample_passage("Lithium mineralisation is hosted within pegmatite.")
    irrelevant = PassageRecord("p2", "doc-test", "test.pdf", 2, 1, "Regional rainfall was measured during field work.")
    results = retrieve_evidence("lithium pegmatite mineralization", [irrelevant, relevant], [], top_k=1)
    assert results[0]["passage"]["passage_id"] == "passage-test"
