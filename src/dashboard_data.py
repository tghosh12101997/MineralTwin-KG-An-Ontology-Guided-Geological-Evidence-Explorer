from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from rdflib import Graph, RDF, RDFS, URIRef


@dataclass(frozen=True)
class DashboardPaths:
    project_root: Path
    processed_dir: Path
    reports_output_dir: Path
    graph_dir: Path
    gempy_dir: Path
    query_dir: Path

    deposits: Path
    sample: Path
    host_rocks: Path
    alterations: Path
    igneous_rocks: Path
    quality_report: Path
    phase2_summary: Path
    phase3_summary: Path
    documents: Path
    passages: Path
    entities: Path
    claims: Path
    review_queue: Path
    review_decisions: Path
    surface_points: Path
    orientations: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "DashboardPaths":
        processed = project_root / "data" / "processed"
        reports_output = processed / "reports"
        graph_dir = processed / "knowledge_graph"
        gempy_dir = project_root / "data" / "gempy"
        return cls(
            project_root=project_root,
            processed_dir=processed,
            reports_output_dir=reports_output,
            graph_dir=graph_dir,
            gempy_dir=gempy_dir,
            query_dir=project_root / "queries",
            deposits=processed / "deposits_clean.csv",
            sample=processed / "deposits_research_sample_50.csv",
            host_rocks=processed / "host_rocks.csv",
            alterations=processed / "alterations.csv",
            igneous_rocks=processed / "associated_igneous_rocks.csv",
            quality_report=processed / "data_quality_report.json",
            phase2_summary=graph_dir / "semantic_summary.json",
            phase3_summary=graph_dir / "phase3_summary.json",
            documents=reports_output / "documents.json",
            passages=reports_output / "passages.jsonl",
            entities=reports_output / "extracted_entities.csv",
            claims=reports_output / "extracted_claims.csv",
            review_queue=reports_output / "review_queue.csv",
            review_decisions=reports_output / "review_decisions.csv",
            surface_points=gempy_dir / "model5_surface_points.csv",
            orientations=gempy_dir / "model5_orientations.csv",
        )


def project_root_from_file(file_path: str | Path) -> Path:
    return Path(file_path).resolve().parent


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def graph_path(paths: DashboardPaths) -> Path | None:
    candidates = [
        paths.graph_dir / "mineraltwin_kg_phase3.ttl",
        paths.graph_dir / "mineraltwin_kg.ttl",
    ]
    return next((path for path in candidates if path.exists()), None)


def load_graph(paths: DashboardPaths) -> Graph:
    graph = Graph()
    selected = graph_path(paths)
    if selected:
        graph.parse(selected, format="turtle")
    return graph


def pipeline_status(paths: DashboardPaths) -> list[dict[str, Any]]:
    checks = [
        ("Phase 1: cleaned deposits", paths.deposits),
        ("Phase 1: research sample", paths.sample),
        ("Phase 2: RDF knowledge graph", paths.graph_dir / "mineraltwin_kg.ttl"),
        ("Phase 2: semantic summary", paths.phase2_summary),
        ("Phase 3: report passages", paths.passages),
        ("Phase 3: extracted claims", paths.claims),
        ("Phase 3: evidence graph", paths.graph_dir / "mineraltwin_kg_phase3.ttl"),
        ("Phase 3: validation", paths.graph_dir / "validation_phase3_report.txt"),
    ]
    return [
        {
            "stage": name,
            "ready": path.exists(),
            "path": str(path.relative_to(paths.project_root)),
        }
        for name, path in checks
    ]


def split_codes(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def commodity_options(deposits: pd.DataFrame) -> list[str]:
    if deposits.empty or "commodity_codes_text" not in deposits.columns:
        return []
    codes: set[str] = set()
    for value in deposits["commodity_codes_text"]:
        codes.update(split_codes(value))
    return sorted(codes)


def filter_deposits(
    deposits: pd.DataFrame,
    commodities: Iterable[str] = (),
    states: Iterable[str] = (),
    provinces: Iterable[str] = (),
    search_text: str = "",
) -> pd.DataFrame:
    if deposits.empty:
        return deposits.copy()
    filtered = deposits.copy()

    selected_commodities = set(commodities)
    if selected_commodities and "commodity_codes_text" in filtered.columns:
        filtered = filtered[
            filtered["commodity_codes_text"].map(
                lambda value: bool(selected_commodities.intersection(split_codes(value)))
            )
        ]

    selected_states = set(states)
    if selected_states and "State" in filtered.columns:
        filtered = filtered[filtered["State"].isin(selected_states)]

    selected_provinces = set(provinces)
    if selected_provinces and "Province" in filtered.columns:
        filtered = filtered[filtered["Province"].isin(selected_provinces)]

    query = search_text.strip()
    if query:
        searchable = [
            column
            for column in (
                "Deposit",
                "District",
                "Province",
                "Subprovince",
                "Principal deposit type",
                "Major/co-products",
            )
            if column in filtered.columns
        ]
        mask = pd.Series(False, index=filtered.index)
        for column in searchable:
            mask |= filtered[column].fillna("").astype(str).str.contains(
                re.escape(query), case=False, regex=True
            )
        filtered = filtered[mask]

    return filtered.reset_index(drop=True)


def deposit_context(
    deposit_id: str,
    host_rocks: pd.DataFrame,
    alterations: pd.DataFrame,
    igneous_rocks: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    def subset(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or "deposit_id" not in frame.columns:
            return pd.DataFrame()
        return frame[frame["deposit_id"].astype(str) == str(deposit_id)].copy()

    return {
        "host_rocks": subset(host_rocks),
        "alterations": subset(alterations),
        "igneous_rocks": subset(igneous_rocks),
    }


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) > 2]


def _fallback_scores(query: str, texts: list[str]) -> list[float]:
    query_counts = Counter(_tokens(query))
    output: list[float] = []
    for text in texts:
        text_counts = Counter(_tokens(text))
        overlap = sum(min(query_counts[token], text_counts[token]) for token in query_counts)
        denominator = math.sqrt(sum(query_counts.values()) * max(1, sum(text_counts.values())))
        output.append(overlap / denominator if denominator else 0.0)
    return output


def retrieve_evidence_from_files(
    query: str,
    passage_records: list[dict[str, Any]],
    claims: pd.DataFrame,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    query = query.strip()
    if not query or not passage_records:
        return []

    texts = [str(record.get("text", "")) for record in passage_records]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=1)
        matrix = vectorizer.fit_transform(texts + [query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel().tolist()
    except (ImportError, ValueError):
        scores = _fallback_scores(query, texts)

    claim_groups: dict[str, list[dict[str, Any]]] = {}
    if not claims.empty and "passage_id" in claims.columns:
        for passage_id, frame in claims.groupby("passage_id", dropna=False):
            claim_groups[str(passage_id)] = frame.fillna("").to_dict(orient="records")

    ranking = sorted(range(len(passage_records)), key=lambda index: scores[index], reverse=True)
    results: list[dict[str, Any]] = []
    for index in ranking[:top_k]:
        passage = passage_records[index]
        passage_id = str(passage.get("passage_id", ""))
        results.append(
            {
                "score": round(float(scores[index]), 4),
                "passage": passage,
                "claims": claim_groups.get(passage_id, []),
            }
        )
    return results


def graph_type_counts(graph: Graph) -> pd.DataFrame:
    if len(graph) == 0:
        return pd.DataFrame(columns=["type", "count"])
    counts: Counter[str] = Counter()
    for _, _, class_uri in graph.triples((None, RDF.type, None)):
        label = next((str(value) for value in graph.objects(class_uri, RDFS.label)), None)
        fallback = str(class_uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        counts[label or fallback] += 1
    return pd.DataFrame(
        [{"type": key, "count": value} for key, value in counts.most_common()]
    )


def graph_node_labels(graph: Graph, limit: int = 400) -> list[tuple[str, str]]:
    if len(graph) == 0:
        return []
    nodes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for subject in graph.subjects():
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        if uri in seen:
            continue
        seen.add(uri)
        label = next((str(value) for value in graph.objects(subject, RDFS.label)), None)
        if label:
            nodes.append((uri, label))
        if len(nodes) >= limit:
            break
    return sorted(nodes, key=lambda item: item[1].casefold())


def graph_neighborhood(graph: Graph, center_uri: str, max_edges: int = 60) -> pd.DataFrame:
    if len(graph) == 0 or not center_uri:
        return pd.DataFrame(columns=["source", "predicate", "target"])
    center = URIRef(center_uri)
    records: list[dict[str, str]] = []

    def display(node: Any) -> str:
        if isinstance(node, URIRef):
            label = next((str(value) for value in graph.objects(node, RDFS.label)), None)
            return label or str(node).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        return str(node)

    for subject, predicate, obj in graph.triples((center, None, None)):
        records.append(
            {"source": display(subject), "predicate": display(predicate), "target": display(obj)}
        )
        if len(records) >= max_edges:
            break
    if len(records) < max_edges:
        for subject, predicate, obj in graph.triples((None, None, center)):
            records.append(
                {"source": display(subject), "predicate": display(predicate), "target": display(obj)}
            )
            if len(records) >= max_edges:
                break
    return pd.DataFrame(records)


def read_query_files(query_dir: Path) -> dict[str, str]:
    if not query_dir.exists():
        return {}
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(query_dir.glob("*.rq"))
    }


def run_select_query(graph: Graph, query_text: str, limit: int = 250) -> pd.DataFrame:
    normalized = re.sub(r"#[^\n]*", "", query_text).strip().casefold()
    if not normalized.startswith(("prefix", "base", "select")) or "select" not in normalized[:1000]:
        raise ValueError("The dashboard only runs SPARQL SELECT queries.")
    if any(keyword in normalized for keyword in ("insert ", "delete ", "load ", "clear ", "drop ", "create ")):
        raise ValueError("Update operations are disabled in the dashboard.")

    result = graph.query(query_text)
    columns = [str(variable) for variable in result.vars]
    records: list[dict[str, Any]] = []
    for row_index, row in enumerate(result):
        if row_index >= limit:
            break
        records.append(
            {
                columns[index]: str(value) if value is not None else None
                for index, value in enumerate(row)
            }
        )
    return pd.DataFrame(records, columns=columns)


def save_review_decision(
    path: Path,
    claim: dict[str, Any],
    decision: str,
    notes: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "claim_id": claim.get("claim_id", ""),
        "passage_id": claim.get("passage_id", ""),
        "document_id": claim.get("document_id", ""),
        "subject_text": claim.get("subject_text", ""),
        "predicate": claim.get("predicate", ""),
        "object_text": claim.get("object_text", ""),
        "confidence": claim.get("confidence", ""),
        "original_review_status": claim.get("review_status", ""),
        "review_decision": decision,
        "review_notes": notes.strip(),
        "reviewed_at_utc": pd.Timestamp.utcnow().isoformat(),
    }
    new_frame = pd.DataFrame([record])
    if path.exists() and path.stat().st_size > 0:
        existing = pd.read_csv(path)
        if "claim_id" in existing.columns and record["claim_id"]:
            existing = existing[existing["claim_id"].astype(str) != str(record["claim_id"])]
        new_frame = pd.concat([existing, new_frame], ignore_index=True)
    new_frame.to_csv(path, index=False)
