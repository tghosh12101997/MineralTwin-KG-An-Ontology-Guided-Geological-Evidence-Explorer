from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from .config import PROCESSED_DIR, REPORTS_DIR

REPORT_OUTPUT_DIR = PROCESSED_DIR / "reports"


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    filename: str
    title: str
    page_count: int
    pages_with_text: int


@dataclass(frozen=True)
class PassageRecord:
    passage_id: str
    document_id: str
    filename: str
    page_number: int
    passage_index: int
    text: str


def _stable_id(prefix: str, value: str, length: int = 16) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def _clean_pdf_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sentence_split(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if part.strip()
    ]


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = _sentence_split(paragraph)
    if len(sentences) <= 1:
        return [paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars)]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        projected = current_len + len(sentence) + (1 if current else 0)
        if current and projected > max_chars:
            chunks.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len = projected
    if current:
        chunks.append(" ".join(current))
    return chunks


def split_page_into_passages(
    text: str,
    min_chars: int = 80,
    max_chars: int = 1200,
) -> list[str]:
    cleaned = _clean_pdf_text(text)
    paragraphs = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n\s*\n", cleaned)
        if part.strip()
    ]

    passages: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) < min_chars:
            buffer = f"{buffer} {paragraph}".strip()
            if len(buffer) < min_chars:
                continue
            paragraph, buffer = buffer, ""
        elif buffer:
            paragraph, buffer = f"{buffer} {paragraph}".strip(), ""

        passages.extend(_split_long_paragraph(paragraph, max_chars=max_chars))

    if buffer and len(buffer) >= 30:
        passages.append(buffer)
    return [p for p in passages if len(p) >= 30]


def discover_reports(report_dir: Path = REPORTS_DIR) -> list[Path]:
    return sorted(
        path for path in report_dir.glob("*.pdf") if path.is_file() and not path.name.startswith("~")
    )


def extract_pdf(path: Path) -> tuple[DocumentRecord, list[PassageRecord]]:
    reader = PdfReader(str(path))
    metadata_title = ""
    if reader.metadata and reader.metadata.title:
        metadata_title = str(reader.metadata.title).strip()
    title = metadata_title or path.stem.replace("_", " ").replace("-", " ")
    document_id = _stable_id("doc", path.name.lower())

    passages: list[PassageRecord] = []
    pages_with_text = 0
    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        if len(raw_text.strip()) < 20:
            continue
        pages_with_text += 1
        for index, passage_text in enumerate(split_page_into_passages(raw_text), start=1):
            passage_id = _stable_id(
                "passage",
                f"{document_id}|{page_number}|{index}|{passage_text[:160]}",
            )
            passages.append(
                PassageRecord(
                    passage_id=passage_id,
                    document_id=document_id,
                    filename=path.name,
                    page_number=page_number,
                    passage_index=index,
                    text=passage_text,
                )
            )

    document = DocumentRecord(
        document_id=document_id,
        filename=path.name,
        title=title,
        page_count=len(reader.pages),
        pages_with_text=pages_with_text,
    )
    return document, passages


def extract_reports(paths: Iterable[Path] | None = None) -> tuple[list[DocumentRecord], list[PassageRecord]]:
    report_paths = list(paths) if paths is not None else discover_reports()
    if not report_paths:
        raise FileNotFoundError(
            "No PDF reports found. Put the two geological PDFs inside `data/reports/` "
            "and run `python run_phase3.py` again."
        )

    documents: list[DocumentRecord] = []
    passages: list[PassageRecord] = []
    for path in report_paths:
        document, document_passages = extract_pdf(path)
        documents.append(document)
        passages.extend(document_passages)
    return documents, passages


def write_report_outputs(
    documents: list[DocumentRecord],
    passages: list[PassageRecord],
) -> tuple[Path, Path]:
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    documents_path = REPORT_OUTPUT_DIR / "documents.json"
    passages_path = REPORT_OUTPUT_DIR / "passages.jsonl"

    documents_path.write_text(
        json.dumps([asdict(item) for item in documents], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with passages_path.open("w", encoding="utf-8") as handle:
        for passage in passages:
            handle.write(json.dumps(asdict(passage), ensure_ascii=False) + "\n")
    return documents_path, passages_path
