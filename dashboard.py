from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard_data import (
    DashboardPaths,
    commodity_options,
    deposit_context,
    filter_deposits,
    graph_neighborhood,
    graph_node_labels,
    graph_path,
    graph_type_counts,
    load_graph,
    pipeline_status,
    read_csv,
    read_json,
    read_jsonl,
    read_query_files,
    retrieve_evidence_from_files,
    run_select_query,
    save_review_decision,
)

PROJECT_ROOT = Path(__file__).resolve().parent
PATHS = DashboardPaths.from_project_root(PROJECT_ROOT)

st.set_page_config(
    page_title="MineralTwin-KG",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --accent: #d69a2d; --panel: rgba(255,255,255,.035); }
      [data-testid="stAppViewContainer"] { background: radial-gradient(circle at 70% 0%, rgba(214,154,45,.08), transparent 34%); }
      [data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,.08); }
      .block-container { padding-top: 1.55rem; padding-bottom: 3rem; max-width: 1500px; }
      .hero { padding: 1.25rem 1.35rem; border: 1px solid rgba(214,154,45,.22); border-radius: 18px; background: linear-gradient(135deg, rgba(214,154,45,.10), rgba(255,255,255,.025)); margin-bottom: 1rem; }
      .hero h1 { margin: 0 0 .35rem 0; letter-spacing: -.035em; }
      .hero p { margin: 0; opacity: .82; max-width: 980px; }
      .eyebrow { color: var(--accent); text-transform: uppercase; letter-spacing: .12em; font-size: .73rem; font-weight: 750; margin-bottom: .5rem; }
      .evidence-card { border: 1px solid rgba(255,255,255,.10); border-radius: 15px; padding: 1rem 1.05rem; background: var(--panel); margin: .65rem 0; }
      .score { color: var(--accent); font-weight: 800; }
      .muted { opacity: .68; }
      .status-ok { color: #5ac98b; font-weight: 700; }
      .status-missing { color: #ef8f8f; font-weight: 700; }
      div[data-testid="stMetric"] { border: 1px solid rgba(255,255,255,.08); background: var(--panel); padding: .8rem 1rem; border-radius: 14px; }
      button[kind="primary"] { border-radius: 999px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_tables() -> dict[str, pd.DataFrame]:
    return {
        "deposits": read_csv(PATHS.deposits),
        "sample": read_csv(PATHS.sample),
        "host_rocks": read_csv(PATHS.host_rocks),
        "alterations": read_csv(PATHS.alterations),
        "igneous_rocks": read_csv(PATHS.igneous_rocks),
        "entities": read_csv(PATHS.entities),
        "claims": read_csv(PATHS.claims),
        "review_queue": read_csv(PATHS.review_queue),
        "surface_points": read_csv(PATHS.surface_points),
        "orientations": read_csv(PATHS.orientations),
    }


@st.cache_data(show_spinner=False)
def load_records() -> dict[str, object]:
    return {
        "quality": read_json(PATHS.quality_report),
        "phase2": read_json(PATHS.phase2_summary),
        "phase3": read_json(PATHS.phase3_summary),
        "documents": read_json(PATHS.documents, default=[]),
        "passages": read_jsonl(PATHS.passages),
    }


@st.cache_resource(show_spinner=False)
def cached_graph():
    return load_graph(PATHS)


def safe_unique(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    return sorted(frame[column].dropna().astype(str).unique().tolist())


def hero(title: str, description: str, eyebrow: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">{html.escape(eyebrow)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def missing_outputs_notice() -> None:
    missing = [row for row in pipeline_status(PATHS) if not row["ready"]]
    if not missing:
        return
    with st.expander("Some pipeline outputs are not ready", expanded=True):
        st.write("Run the missing phases before expecting every dashboard page to contain results.")
        for row in missing:
            st.markdown(f"- `{row['path']}`")
        st.code(
            "python run_pipeline.py\n"
            "python run_semantic_pipeline.py\n"
            "python run_phase3.py",
            language="powershell",
        )


def overview_page(tables: dict[str, pd.DataFrame], records: dict[str, object]) -> None:
    hero(
        "MineralTwin-KG Research Explorer",
        "An evidence-aware interface for mineral-deposit data, geological reports, ontology resources, extracted claims and conceptual 3D model inputs.",
        "Ontology-guided geological evidence explorer",
    )
    missing_outputs_notice()

    phase3 = records["phase3"] if isinstance(records["phase3"], dict) else {}
    graph = cached_graph()
    deposits = tables["deposits"]
    metrics = [
        ("Deposits", len(deposits)),
        ("RDF triples", len(graph)),
        ("Report passages", len(records["passages"])),
        ("Extracted entities", len(tables["entities"])),
        ("Evidence claims", len(tables["claims"])),
        ("Claims for review", int(phase3.get("claims_needing_review", len(tables["review_queue"])))),
    ]
    columns = st.columns(6)
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, f"{value:,}")

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        st.subheader("Research workflow")
        st.graphviz_chart(
            """
            digraph G {
              rankdir=LR;
              graph [bgcolor="transparent", pad="0.25", nodesep="0.45", ranksep="0.65"];
              node [shape=box, style="rounded,filled", fillcolor="#24272d", fontcolor="white", color="#555b66", margin="0.14"];
              edge [color="#d69a2d", penwidth=1.5, arrowsize=0.75];
              A [label="Mineral deposit\nspreadsheets"];
              B [label="Clean normalized\ntables"];
              C [label="OWL/RDF knowledge\ngraph"];
              D [label="Geological PDF\nreports"];
              E [label="Passages, entities\nand claims"];
              F [label="Evidence retrieval\nand review"];
              G [label="3D geological\nmodel inputs"];
              A -> B -> C;
              D -> E -> C;
              C -> F;
              E -> F;
              C -> G;
            }
            """
        )
    with right:
        st.subheader("Pipeline readiness")
        status_frame = pd.DataFrame(pipeline_status(PATHS))
        for row in status_frame.to_dict(orient="records"):
            status_class = "status-ok" if row["ready"] else "status-missing"
            symbol = "Ready" if row["ready"] else "Missing"
            st.markdown(
                f"<span class='{status_class}'>{symbol}</span> &nbsp; {html.escape(row['stage'])}",
                unsafe_allow_html=True,
            )
            st.caption(row["path"])

    st.subheader("What this prototype demonstrates")
    a, b, c = st.columns(3, gap="large")
    a.markdown("**Semantic integration**\n\nDeposits, commodities, host rocks, alteration and provenance are represented through stable RDF resources.")
    b.markdown("**Evidence-aware extraction**\n\nReport-derived relations remain reified claims with page provenance, confidence and review status.")
    c.markdown("**Human-in-the-loop modelling**\n\nUncertain claims are routed to review instead of being silently asserted as geological facts.")


def deposit_explorer_page(tables: dict[str, pd.DataFrame]) -> None:
    hero(
        "Deposit Explorer",
        "Filter the Australian deposit compilation, inspect spatial patterns and move from a map marker to its host-rock, alteration and igneous-rock context.",
        "Structured geological data",
    )
    deposits = tables["deposits"]
    if deposits.empty:
        st.warning("Run `python run_pipeline.py` first. The cleaned deposit table is missing.")
        return

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.25, 1, 1.2, 1.3])
        selected_commodities = c1.multiselect(
            "Commodity",
            commodity_options(deposits),
            default=[code for code in ("Li", "Cu", "Ni") if code in commodity_options(deposits)],
        )
        selected_states = c2.multiselect("State", safe_unique(deposits, "State"))
        selected_provinces = c3.multiselect("Province", safe_unique(deposits, "Province"))
        search_text = c4.text_input("Search", placeholder="Deposit, district, type or province")

    filtered = filter_deposits(
        deposits,
        commodities=selected_commodities,
        states=selected_states,
        provinces=selected_provinces,
        search_text=search_text,
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Visible deposits", len(filtered))
    m2.metric("Provinces", filtered["Province"].nunique() if "Province" in filtered else 0)
    m3.metric("States", filtered["State"].nunique() if "State" in filtered else 0)

    map_frame = filtered.copy()
    if {"Latitude", "Longitude"}.issubset(map_frame.columns):
        map_frame = map_frame.dropna(subset=["Latitude", "Longitude"])
    if not map_frame.empty:
        hover_columns = [
            column
            for column in ("Deposit", "State", "Province", "Principal deposit type", "Major/co-products")
            if column in map_frame.columns
        ]
        figure = px.scatter_geo(
            map_frame,
            lat="Latitude",
            lon="Longitude",
            hover_name="Deposit" if "Deposit" in map_frame.columns else None,
            hover_data=hover_columns,
            color="State" if "State" in map_frame.columns else None,
            projection="natural earth",
            title="Australian mineral deposits",
        )
        figure.update_geos(
            scope="world",
            lataxis_range=[-46, -8],
            lonaxis_range=[110, 156],
            showcountries=True,
            showcoastlines=True,
            fitbounds=False,
        )
        figure.update_layout(height=580, margin=dict(l=0, r=0, t=50, b=0), legend_title_text="State")
        st.plotly_chart(figure, width="stretch")
    else:
        st.info("No deposits match the current filters.")
        return

    table_columns = [
        column
        for column in (
            "deposit_id",
            "Deposit",
            "State",
            "Province",
            "Principal deposit type",
            "Major/co-products",
            "commodity_codes_text",
            "Latitude",
            "Longitude",
        )
        if column in filtered.columns
    ]
    st.dataframe(filtered[table_columns], width="stretch", hide_index=True)

    st.subheader("Deposit detail")
    label_to_id = {
        f"{row.get('Deposit', row.get('deposit_id'))} · {row.get('State', '')}": str(row["deposit_id"])
        for _, row in filtered.iterrows()
        if pd.notna(row.get("deposit_id"))
    }
    if not label_to_id:
        st.warning("No deposits with valid identifiers match the current filters.")
        return

    selected_label = st.selectbox("Choose a deposit", list(label_to_id.keys()))
    selected_id = label_to_id[selected_label]
    selected_matches = filtered[filtered["deposit_id"].astype(str) == selected_id]
    if selected_matches.empty:
        st.warning("The selected deposit could not be found in the filtered dataset.")
        return
    selected_row = selected_matches.iloc[0]

    detail_columns = st.columns(4)
    detail_columns[0].metric("Deposit", str(selected_row.get("Deposit", "Unknown")))
    detail_columns[1].metric("State", str(selected_row.get("State", "Unknown")))
    detail_columns[2].metric("Province", str(selected_row.get("Province", "Unknown")))
    detail_columns[3].metric("Commodities", str(selected_row.get("commodity_codes_text", "Unknown")))

    context = deposit_context(
        selected_id,
        tables["host_rocks"],
        tables["alterations"],
        tables["igneous_rocks"],
    )
    tabs = st.tabs(["Record", "Host rocks", "Alteration", "Associated igneous rocks"])
    with tabs[0]:
        record = selected_row.dropna().astype(str).to_frame(name="value").reset_index()
        record = record.rename(columns={"index": "field"})
        st.dataframe(record, width="stretch", hide_index=True)
    with tabs[1]:
        st.dataframe(context["host_rocks"], width="stretch", hide_index=True)
    with tabs[2]:
        st.dataframe(context["alterations"], width="stretch", hide_index=True)
    with tabs[3]:
        st.dataframe(context["igneous_rocks"], width="stretch", hide_index=True)


def evidence_page(tables: dict[str, pd.DataFrame], records: dict[str, object]) -> None:
    hero(
        "Geological Evidence Search",
        "Search the extracted report passages and inspect the provenance-aware claims attached to each result. This is retrieval over evidence, not an unrestricted chatbot.",
        "Report NLP and grounded retrieval",
    )
    passages = records["passages"] if isinstance(records["passages"], list) else []
    claims = tables["claims"]
    if not passages:
        st.warning("Run `python run_phase3.py` first. No report passages are available.")
        return

    examples = [
        "Which passages discuss lithium mineralisation hosted by pegmatite?",
        "What geological structures control mineralisation?",
        "Which alteration types are associated with mineralisation?",
        "Where are spodumene and pegmatite mentioned together?",
    ]
    query = st.text_input("Research question", value=examples[0])
    top_k = st.slider("Number of evidence passages", min_value=3, max_value=12, value=5)
    search = st.button("Search evidence", type="primary", width="content")

    if search or query:
        results = retrieve_evidence_from_files(query, passages, claims, top_k=top_k)
        if not results:
            st.info("No evidence passages were returned.")
            return
        for rank, result in enumerate(results, start=1):
            passage = result["passage"]
            filename = str(passage.get("filename", "Unknown document"))
            page_number = passage.get("page_number", "?")
            score = float(result.get("score", 0.0))
            st.markdown(
                f"""
                <div class="evidence-card">
                  <div><span class="score">Result {rank} · score {score:.3f}</span></div>
                  <div class="muted">{html.escape(filename)} · page {page_number}</div>
                  <p>{html.escape(str(passage.get('text', '')))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            attached_claims = result.get("claims", [])
            if attached_claims:
                claim_frame = pd.DataFrame(attached_claims)
                visible = [
                    column
                    for column in (
                        "subject_text",
                        "predicate",
                        "object_text",
                        "confidence",
                        "review_status",
                        "extraction_method",
                    )
                    if column in claim_frame.columns
                ]
                st.dataframe(claim_frame[visible], width="stretch", hide_index=True)
            else:
                st.caption("No relation claim was extracted from this passage.")


def knowledge_graph_page() -> None:
    hero(
        "Knowledge Graph Workbench",
        "Inspect RDF type distributions, explore the neighborhood around a labelled resource and run read-only SPARQL competency queries.",
        "OWL, RDF, SHACL and SPARQL",
    )
    graph = cached_graph()
    selected_path = graph_path(PATHS)
    if len(graph) == 0:
        st.warning("Run `python run_semantic_pipeline.py` and then `python run_phase3.py` first.")
        return
    st.caption(f"Loaded `{selected_path.relative_to(PROJECT_ROOT)}`")

    c1, c2, c3 = st.columns(3)
    c1.metric("Triples", f"{len(graph):,}")
    c2.metric("URI subjects", f"{len(set(graph.subjects())):,}")
    c3.metric("Predicates", f"{len(set(graph.predicates())):,}")

    counts = graph_type_counts(graph).head(20)
    if not counts.empty:
        figure = px.bar(counts.sort_values("count"), x="count", y="type", orientation="h", title="Most frequent RDF types")
        figure.update_layout(height=570, margin=dict(l=0, r=0, t=50, b=0), yaxis_title=None)
        st.plotly_chart(figure, width="stretch")

    st.subheader("Resource neighborhood")
    nodes = graph_node_labels(graph)
    if nodes:
        labels = [label for _, label in nodes]
        label_to_uri = {f"{label} · {uri.rsplit('/', 1)[-1]}": uri for uri, label in nodes}
        selected = st.selectbox("Choose a labelled resource", list(label_to_uri.keys()))
        neighborhood = graph_neighborhood(graph, label_to_uri[selected])
        st.dataframe(neighborhood, width="stretch", hide_index=True)

    st.subheader("SPARQL query runner")
    query_files = read_query_files(PATHS.query_dir)
    choices = ["Custom SELECT query"] + list(query_files.keys())
    selected_query = st.selectbox("Query", choices)
    default_query = query_files.get(selected_query, "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 50")
    query_text = st.text_area("SPARQL", value=default_query, height=260)
    if st.button("Run SELECT query", type="primary"):
        try:
            result = run_select_query(graph, query_text)
            st.success(f"Returned {len(result)} rows.")
            st.dataframe(result, width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Query failed: {exc}")


def review_page(tables: dict[str, pd.DataFrame]) -> None:
    hero(
        "Claim Review Queue",
        "Review uncertain report-derived relations before they are promoted into accepted geological knowledge. Decisions are stored separately from the original extraction output.",
        "Human-in-the-loop validation",
    )
    claims = tables["claims"]
    review_queue = tables["review_queue"]
    if claims.empty:
        st.warning("Run `python run_phase3.py` first. No claims are available.")
        return

    if review_queue.empty and "review_status" in claims.columns:
        review_queue = claims[claims["review_status"].astype(str) == "needs-review"].copy()
    if review_queue.empty:
        st.success("No claims currently require manual review.")
        return

    f1, f2 = st.columns(2)
    predicates = safe_unique(review_queue, "predicate")
    selected_predicates = f1.multiselect("Predicate", predicates, default=predicates)
    maximum_confidence = float(pd.to_numeric(review_queue["confidence"], errors="coerce").max()) if "confidence" in review_queue else 1.0
    confidence_limit = f2.slider("Maximum confidence", 0.0, 1.0, min(maximum_confidence, 0.85), 0.01)

    filtered = review_queue.copy()
    if selected_predicates and "predicate" in filtered.columns:
        filtered = filtered[filtered["predicate"].isin(selected_predicates)]
    if "confidence" in filtered.columns:
        filtered = filtered[pd.to_numeric(filtered["confidence"], errors="coerce") <= confidence_limit]
    filtered = filtered.reset_index(drop=True)

    st.metric("Claims awaiting review", len(filtered))
    if filtered.empty:
        st.info("No claims match the current filters.")
        return

    label_to_index = {
        f"{row.get('subject_text', '?')} → {row.get('predicate', '?')} → {row.get('object_text', '?')} · {float(row.get('confidence', 0)):.2f}": index
        for index, row in filtered.iterrows()
    }
    selected_label = st.selectbox("Claim", list(label_to_index.keys()))
    claim = filtered.iloc[label_to_index[selected_label]].fillna("").to_dict()

    c1, c2, c3 = st.columns(3)
    c1.metric("Subject", str(claim.get("subject_text", "")))
    c2.metric("Relation", str(claim.get("predicate", "")))
    c3.metric("Object", str(claim.get("object_text", "")))
    st.markdown(f"**Source sentence:** {html.escape(str(claim.get('source_text', '')))}")
    st.caption(
        f"Document {claim.get('document_id', '')} · page {claim.get('page_number', '')} · "
        f"confidence {claim.get('confidence', '')} · method {claim.get('extraction_method', '')}"
    )

    decision = st.radio("Decision", ["accept", "reject", "needs-domain-expert"], horizontal=True)
    notes = st.text_area("Reviewer notes", placeholder="Explain the geological or extraction reasoning behind the decision.")
    if st.button("Save review decision", type="primary"):
        save_review_decision(PATHS.review_decisions, claim, decision, notes)
        st.success(f"Decision saved to `{PATHS.review_decisions.relative_to(PROJECT_ROOT)}`.")
        st.cache_data.clear()

    if PATHS.review_decisions.exists():
        st.subheader("Saved decisions")
        st.dataframe(read_csv(PATHS.review_decisions), width="stretch", hide_index=True)


def model_page(tables: dict[str, pd.DataFrame]) -> None:
    hero(
        "Conceptual 3D Model Inputs",
        "Inspect the surface points and geological orientations used by the GemPy fault example. This page visualizes the modelling evidence; full implicit interpolation is the next implementation step.",
        "Semantic-to-3D bridge",
    )
    surfaces = tables["surface_points"]
    orientations = tables["orientations"]
    if surfaces.empty:
        st.warning("Place `model5_surface_points.csv` and `model5_orientations.csv` in `data/gempy/`.")
        return

    required = {"X", "Y", "Z"}
    if not required.issubset(surfaces.columns):
        st.error(f"Surface-point file must contain {sorted(required)}.")
        return

    formation_column = "formation" if "formation" in surfaces.columns else None
    figure = px.scatter_3d(
        surfaces,
        x="X",
        y="Y",
        z="Z",
        color=formation_column,
        hover_data=[formation_column] if formation_column else None,
        title="GemPy surface points and fault observations",
    )
    figure.update_traces(marker=dict(size=6))

    if not orientations.empty and required.issubset(orientations.columns):
        figure.add_trace(
            go.Scatter3d(
                x=orientations["X"],
                y=orientations["Y"],
                z=orientations["Z"],
                mode="markers",
                marker=dict(size=8, symbol="diamond"),
                name="Orientation measurements",
                text=(orientations[formation_column].astype(str) if formation_column and formation_column in orientations else None),
            )
        )
    figure.update_layout(height=700, margin=dict(l=0, r=0, t=55, b=0))
    st.plotly_chart(figure, width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Surface points")
        st.dataframe(surfaces, width="stretch", hide_index=True)
    with right:
        st.subheader("Orientations")
        st.dataframe(orientations, width="stretch", hide_index=True)

    st.info(
        "This is intentionally labelled a conceptual model-input viewer. The next phase can run GemPy to interpolate the units and fault, then link ontology resources such as `MainFault` to model elements."
    )


def methods_page(records: dict[str, object]) -> None:
    hero(
        "Methods and Reproducibility",
        "A compact record of the project question, design decisions, provenance model and current limitations.",
        "Research documentation",
    )
    st.subheader("Research question")
    st.markdown(
        "> How can ontology constraints, geospatial knowledge graphs and provenance-aware retrieval improve the extraction and use of geological evidence in early-stage mineral-system modelling?"
    )

    st.subheader("Design decisions")
    st.markdown(
        """
        1. Structured deposit data is normalized before semantic conversion.
        2. Report-derived relations are represented as `ExtractedClaim` resources rather than immediately asserted facts.
        3. Each claim records source text, report passage, page number, confidence, extraction method and review status.
        4. SHACL checks structural completeness, while the review queue addresses semantic uncertainty.
        5. Evidence retrieval returns passages and claims together so users can inspect why a result was surfaced.
        """
    )

    st.subheader("Current limitations")
    st.markdown(
        """
        - Entity and relation extraction is lexicon and pattern based; it is transparent but not yet a trained geological NLP model.
        - The report parser expects selectable PDF text and does not perform OCR.
        - Retrieval currently uses TF-IDF rather than dense embeddings or an external language model.
        - The 3D page visualizes GemPy inputs but does not yet execute the full implicit geological interpolation.
        - Review decisions are stored separately and are not yet written back into the RDF graph.
        """
    )

    st.subheader("Phase 3 run summary")
    phase3 = records["phase3"] if isinstance(records["phase3"], dict) else {}
    st.json(phase3 or {"status": "Phase 3 summary not available yet."})


TABLES = load_tables()
RECORDS = load_records()

st.sidebar.markdown("## MineralTwin-KG")
st.sidebar.caption("Research prototype · July 2026")
page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Deposit Explorer",
        "Evidence Search",
        "Knowledge Graph",
        "Claim Review",
        "3D Model Inputs",
        "Methods",
    ],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption("Run the data pipelines before opening the dashboard for the first time.")
if st.sidebar.button("Reload project files"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

if page == "Overview":
    overview_page(TABLES, RECORDS)
elif page == "Deposit Explorer":
    deposit_explorer_page(TABLES)
elif page == "Evidence Search":
    evidence_page(TABLES, RECORDS)
elif page == "Knowledge Graph":
    knowledge_graph_page()
elif page == "Claim Review":
    review_page(TABLES)
elif page == "3D Model Inputs":
    model_page(TABLES)
else:
    methods_page(RECORDS)
