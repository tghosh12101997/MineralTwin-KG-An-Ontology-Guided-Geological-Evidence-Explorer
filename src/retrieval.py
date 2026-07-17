from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict

from .domain_extraction import ExtractedClaimRecord
from .report_extraction import PassageRecord


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) > 2]


def _fallback_scores(query: str, passages: list[PassageRecord]) -> list[float]:
    query_counts = Counter(_tokens(query))
    scores: list[float] = []
    for passage in passages:
        passage_counts = Counter(_tokens(passage.text))
        overlap = sum(min(query_counts[t], passage_counts[t]) for t in query_counts)
        denominator = math.sqrt(sum(query_counts.values()) * max(1, sum(passage_counts.values())))
        scores.append(overlap / denominator if denominator else 0.0)
    return scores


def retrieve_evidence(
    query: str,
    passages: list[PassageRecord],
    claims: list[ExtractedClaimRecord],
    top_k: int = 5,
) -> list[dict[str, object]]:
    if not passages:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
        matrix = vectorizer.fit_transform([item.text for item in passages] + [query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel().tolist()
    except (ImportError, ValueError):
        scores = _fallback_scores(query, passages)

    claim_map: dict[str, list[ExtractedClaimRecord]] = {}
    for claim in claims:
        claim_map.setdefault(claim.passage_id, []).append(claim)

    ranking = sorted(range(len(passages)), key=lambda index: scores[index], reverse=True)[:top_k]
    output: list[dict[str, object]] = []
    for index in ranking:
        passage = passages[index]
        output.append(
            {
                "score": round(float(scores[index]), 4),
                "passage": asdict(passage),
                "claims": [asdict(item) for item in claim_map.get(passage.passage_id, [])],
            }
        )
    return output
