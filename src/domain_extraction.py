from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import PROCESSED_DIR, PROJECT_ROOT
from .report_extraction import PassageRecord

LEXICON_PATH = PROJECT_ROOT / "data" / "lexicons" / "geology_terms.json"
DEPOSIT_SAMPLE_PATH = PROCESSED_DIR / "deposits_research_sample_50.csv"

ENTITY_CLASS_PRIORITY = {
    "DEPOSIT": 8,
    "MINERALIZATION": 7,
    "COMMODITY": 6,
    "MINERAL": 5,
    "LITHOLOGY": 4,
    "ALTERATION": 3,
    "STRUCTURE": 2,
    "GEOCHEMICAL_VALUE": 1,
}

COMMODITY_CODES = {
    "lithium": "Li", "nickel": "Ni", "copper": "Cu", "cobalt": "Co",
    "gold": "Au", "tantalum": "Ta", "tin": "Sn", "silver": "Ag",
    "zinc": "Zn", "lead": "Pb", "molybdenum": "Mo", "tungsten": "W",
    "uranium": "U", "beryllium": "Be", "rare earth elements": "REE",
    "rare-earth elements": "REE", "ree": "REE",
}


@dataclass(frozen=True)
class EntityMention:
    entity_id: str
    passage_id: str
    document_id: str
    page_number: int
    entity_type: str
    text: str
    normalized_text: str
    start: int
    end: int


@dataclass(frozen=True)
class ExtractedClaimRecord:
    claim_id: str
    passage_id: str
    document_id: str
    page_number: int
    subject_id: str
    subject_text: str
    subject_type: str
    predicate: str
    object_id: str
    object_text: str
    object_type: str
    confidence: float
    extraction_method: str
    source_text: str
    review_status: str


def stable_id(prefix: str, value: str, length: int = 16) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:length]}"


def normalize_term(text: str) -> str:
    normalized = text.casefold().replace("–", "-").replace("—", "-")
    normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;()[]{}")
    spelling = {
        "mineralisation": "mineralization",
        "mineralised": "mineralized",
        "albitisation": "albitization",
        "greisenisation": "greisenization",
        "tourmalinisation": "tourmalinization",
        "dike": "dyke",
    }
    return spelling.get(normalized, normalized)


def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing geology lexicon: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: sorted(set(values), key=len, reverse=True) for key, values in raw.items()}


def load_deposit_terms() -> dict[str, str]:
    if not DEPOSIT_SAMPLE_PATH.exists():
        return {}
    frame = pd.read_csv(DEPOSIT_SAMPLE_PATH)
    mapping: dict[str, str] = {}
    for _, row in frame.iterrows():
        label = str(row.get("Deposit", "")).strip()
        deposit_id = str(row.get("deposit_id", "")).strip()
        if len(label) >= 3 and deposit_id:
            mapping[label] = deposit_id
    return mapping


def _phrase_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s\-]+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def _remove_overlaps(candidates: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    ranked = sorted(
        candidates,
        key=lambda item: (-(item[1] - item[0]), -ENTITY_CLASS_PRIORITY.get(item[2], 0), item[0]),
    )
    selected: list[tuple[int, int, str, str]] = []
    for candidate in ranked:
        start, end, _, _ = candidate
        if any(not (end <= s or start >= e) for s, e, _, _ in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: item[0])


def extract_entities_from_text(
    passage: PassageRecord,
    lexicon: dict[str, list[str]] | None = None,
    deposit_terms: dict[str, str] | None = None,
) -> list[EntityMention]:
    lexicon = lexicon or load_lexicon()
    deposit_terms = deposit_terms if deposit_terms is not None else load_deposit_terms()
    candidates: list[tuple[int, int, str, str]] = []

    for label, deposit_id in deposit_terms.items():
        for match in _phrase_pattern(label).finditer(passage.text):
            candidates.append((match.start(), match.end(), "DEPOSIT", deposit_id))

    for entity_type, terms in lexicon.items():
        for term in terms:
            for match in _phrase_pattern(term).finditer(passage.text):
                candidates.append((match.start(), match.end(), entity_type, term))

    assay_pattern = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:wt\.?\s*)?(?:%|ppm|ppb|g/t)\s*(?:Li2O|Li|Cu|Ni|Co|Au|Ta|Sn|Zn|Pb)?\b",
        re.IGNORECASE,
    )
    for match in assay_pattern.finditer(passage.text):
        candidates.append((match.start(), match.end(), "GEOCHEMICAL_VALUE", match.group(0)))

    mentions: list[EntityMention] = []
    for start, end, entity_type, canonical in _remove_overlaps(candidates):
        text = passage.text[start:end]
        normalized = normalize_term(text)
        if entity_type == "DEPOSIT":
            entity_id = f"deposit:{canonical}"
        elif entity_type == "COMMODITY":
            code = COMMODITY_CODES.get(normalized, normalized)
            entity_id = f"commodity:{code}"
        else:
            entity_id = stable_id(entity_type.lower(), normalized)
        mentions.append(
            EntityMention(
                entity_id=entity_id,
                passage_id=passage.passage_id,
                document_id=passage.document_id,
                page_number=passage.page_number,
                entity_type=entity_type,
                text=text,
                normalized_text=normalized,
                start=start,
                end=end,
            )
        )
    return mentions


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for match in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9])", text):
        end = match.start()
        sentence = text[cursor:end].strip()
        if sentence:
            leading = len(text[cursor:end]) - len(text[cursor:end].lstrip())
            spans.append((cursor + leading, end, sentence))
        cursor = match.end()
    final = text[cursor:].strip()
    if final:
        leading = len(text[cursor:]) - len(text[cursor:].lstrip())
        spans.append((cursor + leading, len(text), final))
    return spans or [(0, len(text), text)]


def _first_of(entities: list[EntityMention], types: tuple[str, ...]) -> EntityMention | None:
    for entity_type in types:
        for entity in entities:
            if entity.entity_type == entity_type:
                return entity
    return None


def _nearest(entities: list[EntityMention], entity_type: str, pivot: int) -> EntityMention | None:
    matching = [entity for entity in entities if entity.entity_type == entity_type]
    if not matching:
        return None
    return min(matching, key=lambda entity: abs(((entity.start + entity.end) // 2) - pivot))


def _claim(
    passage: PassageRecord,
    subject: EntityMention,
    predicate: str,
    obj: EntityMention,
    confidence: float,
    method: str,
    sentence: str,
) -> ExtractedClaimRecord:
    key = f"{passage.passage_id}|{subject.entity_id}|{predicate}|{obj.entity_id}|{sentence}"
    return ExtractedClaimRecord(
        claim_id=stable_id("claim", key),
        passage_id=passage.passage_id,
        document_id=passage.document_id,
        page_number=passage.page_number,
        subject_id=subject.entity_id,
        subject_text=subject.text,
        subject_type=subject.entity_type,
        predicate=predicate,
        object_id=obj.entity_id,
        object_text=obj.text,
        object_type=obj.entity_type,
        confidence=round(confidence, 2),
        extraction_method=method,
        source_text=sentence,
        review_status="accepted-auto" if confidence >= 0.85 else "needs-review",
    )


def extract_claims_from_passage(
    passage: PassageRecord,
    entities: list[EntityMention],
) -> list[ExtractedClaimRecord]:
    claims: list[ExtractedClaimRecord] = []
    for sentence_start, sentence_end, sentence in _sentence_spans(passage.text):
        sent_entities = [
            entity for entity in entities if entity.start >= sentence_start and entity.end <= sentence_end
        ]
        if len(sent_entities) < 2:
            continue
        sentence_lower = sentence.casefold()
        pivot = sentence_start + (sentence_end - sentence_start) // 2
        subject = _first_of(sent_entities, ("DEPOSIT", "MINERALIZATION", "COMMODITY", "MINERAL"))

        if subject and any(token in sentence_lower for token in ("hosted by", "hosted in", "hosted within", "occurs in", "occur within", "contained in")):
            obj = _nearest(sent_entities, "LITHOLOGY", pivot)
            if obj:
                claims.append(_claim(passage, subject, "hostedBy", obj, 0.90, "explicit-host-pattern", sentence))

        alteration = _nearest(sent_entities, "ALTERATION", pivot)
        if subject and alteration:
            explicit = any(
                token in sentence_lower
                for token in ("associated with", "accompanied by", "characterised by", "characterized by", "altered by")
            )
            confidence = 0.86 if explicit else 0.64
            method = "explicit-alteration-pattern" if explicit else "sentence-cooccurrence-alteration"
            claims.append(_claim(passage, subject, "associatedWithAlteration", alteration, confidence, method, sentence))

        structure = _nearest(sent_entities, "STRUCTURE", pivot)
        if subject and structure:
            explicit = any(
                token in sentence_lower
                for token in ("controlled by", "structurally controlled", "along the", "along a", "adjacent to", "related to")
            )
            if explicit:
                claims.append(_claim(passage, subject, "controlledByStructure", structure, 0.87, "explicit-structure-pattern", sentence))

        mineral = _nearest(sent_entities, "MINERAL", pivot)
        mineral_subject = _first_of(sent_entities, ("DEPOSIT", "MINERALIZATION", "LITHOLOGY"))
        if mineral_subject and mineral and mineral_subject.entity_id != mineral.entity_id:
            explicit = any(
                token in sentence_lower
                for token in ("contains", "comprises", "composed of", "bearing", "rich in", "includes")
            )
            if explicit:
                claims.append(_claim(passage, mineral_subject, "containsMineral", mineral, 0.84, "explicit-mineral-pattern", sentence))

        assay = _nearest(sent_entities, "GEOCHEMICAL_VALUE", pivot)
        geochem_subject = _first_of(sent_entities, ("DEPOSIT", "MINERALIZATION", "COMMODITY", "MINERAL"))
        if assay and geochem_subject:
            claims.append(_claim(passage, geochem_subject, "hasGeochemicalEvidence", assay, 0.82, "assay-pattern", sentence))

    unique: dict[tuple[str, str, str, str], ExtractedClaimRecord] = {}
    for item in claims:
        key = (item.passage_id, item.subject_id, item.predicate, item.object_id)
        existing = unique.get(key)
        if existing is None or item.confidence > existing.confidence:
            unique[key] = item
    return list(unique.values())


def extract_corpus(
    passages: Iterable[PassageRecord],
) -> tuple[list[EntityMention], list[ExtractedClaimRecord]]:
    lexicon = load_lexicon()
    deposit_terms = load_deposit_terms()
    all_entities: list[EntityMention] = []
    all_claims: list[ExtractedClaimRecord] = []
    for passage in passages:
        entities = extract_entities_from_text(passage, lexicon=lexicon, deposit_terms=deposit_terms)
        claims = extract_claims_from_passage(passage, entities)
        all_entities.extend(entities)
        all_claims.extend(claims)
    return all_entities, all_claims


def write_extraction_outputs(
    entities: list[EntityMention],
    claims: list[ExtractedClaimRecord],
) -> tuple[Path, Path, Path]:
    output_dir = PROCESSED_DIR / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    entity_path = output_dir / "extracted_entities.csv"
    claim_path = output_dir / "extracted_claims.csv"
    review_path = output_dir / "review_queue.csv"

    entity_frame = pd.DataFrame([asdict(item) for item in entities])
    claim_frame = pd.DataFrame([asdict(item) for item in claims])
    entity_frame.to_csv(entity_path, index=False)
    claim_frame.to_csv(claim_path, index=False)
    if claim_frame.empty:
        claim_frame.to_csv(review_path, index=False)
    else:
        claim_frame.sort_values(["confidence", "document_id", "page_number"]).query(
            "review_status == 'needs-review'"
        ).to_csv(review_path, index=False)
    return entity_path, claim_path, review_path
