from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.config import PROCESSED_DIR
from src.domain_extraction import ExtractedClaimRecord
from src.report_extraction import PassageRecord
from src.retrieval import retrieve_evidence


def load_passages(path: Path) -> list[PassageRecord]:
    passages: list[PassageRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                passages.append(PassageRecord(**json.loads(line)))
    return passages


def load_claims(path: Path) -> list[ExtractedClaimRecord]:
    claims: list[ExtractedClaimRecord] = []
    if not path.exists() or path.stat().st_size == 0:
        return claims
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row["page_number"] = int(row["page_number"])
            row["confidence"] = float(row["confidence"])
            claims.append(ExtractedClaimRecord(**row))
    return claims


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve report passages and structured claims.")
    parser.add_argument("query", help="Natural-language geological question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    report_dir = PROCESSED_DIR / "reports"
    passages = load_passages(report_dir / "passages.jsonl")
    claims = load_claims(report_dir / "extracted_claims.csv")
    print(json.dumps(retrieve_evidence(args.query, passages, claims, args.top_k), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
