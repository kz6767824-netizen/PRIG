import streamlit.components.v1 as components
import streamlit as st
import sys
import os

# Add agent folder to Python path
AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent")
sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from parse_migration import parse_multi_table_migration
from report_builder import (
    build_full_report,
    get_multi_hop_downstream,
    format_lineage_chains,
)
from severity import classify_migration
from severity_rollup import compute_overall_severity
from write_back_tag import write_back_tag
from write_back_context_document import write_back_context_document, write_back_combined_context_document

from lineage_graph import build_mermaid_graph

DATAHUB_TOKEN = os.environ.get("DATAHUB_TOKEN", "")
MAX_LINEAGE_HOPS = int(os.environ.get("koza_MAX_LINEAGE_HOPS", "2"))


def render_mermaid(mermaid_code: str, height: int = 320):
    html = f"""
    <div class="mermaid">
    {mermaid_code}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{ startOnLoad: true }});</script>
    """
    components.html(html, height=height, scrolling=True)


st.set_page_config(page_title="koza Impact Guardian", layout="centered")
st.title("🛡️ koza")
st.caption("One bad ALTER TABLE can silently break every downstream dashboard. Don't let a DROP COLUMN become a production incident. This agent stops it before merge.")

# --- Sidebar controls ---
st.sidebar.header("Settings")
dry_run = st.sidebar.checkbox("🔒 Dry run (don't write to DataHub)", value=True)
use_llm = st.sidebar.checkbox(
    "✨ Use LLM for explanations (Groq)",
    value=False,
    help="If unchecked, uses the deterministic template. If checked but no "
         "GROQ_API_KEY is set (or the call fails), automatically falls back "
         "to the template -- the report never breaks either way."
)
save_context_doc = st.sidebar.checkbox(
    "📄 Enable Context Document saving",
    value=False,
    help="When on and Dry run is off, automatically saves a Context "
         "Document the moment you click 'Check Impact' -- ONE combined "
         "document covering every table if the migration touches more "
         "than one, or a single document if it touches just one. For "
         "multi-table migrations, each table's detail view also offers an "
         "extra button to save that table separately. In addition to (not "
         "instead of) each table's severity tag. Off by default since each "
         "save creates a new document (no update-in-place yet)."
)
show_details = st.sidebar.checkbox("Show technical details", value=False)
max_hops_input = st.sidebar.number_input(
    "Lineage hops", min_value=1, max_value=5, value=MAX_LINEAGE_HOPS,
    help="How many downstream hops to traverse (e.g. 2 = table -> dashboard -> KPI rollup)."
)

st.sidebar.markdown("---")
st.sidebar.markdown("**How it works:**")
st.sidebar.markdown("""
1. Paste your SQL migration -- one or more statements, one or more tables
2. We parse every statement and check DataHub's real schema + multi-hop lineage
3. You get a severity verdict and impact report, per table
4. If not dry-run, we tag each affected dataset in DataHub (auto-creating the
   tag if needed) and optionally save a Context Document
""")

# --- Main form ---
st.markdown("### Migration Input")

manual_table_name = st.text_input(
    "Table name (for Tag management below only)",
    value="orders",
    help="Used only by the manual 'Tag management' tool below, not by the "
         "analysis -- analysis now detects every table in your SQL automatically."
)
manual_dataset_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{manual_table_name},PROD)"

st.markdown("---")
with st.expander("🧹 Tag management"):
    st.caption(f"Applies to: `{manual_dataset_urn}`")
    if st.button("Clear all review tags from this dataset"):
        with st.spinner("Removing tags..."):
            try:
                client = DataHubClient(server="http://localhost:8081", token=DATAHUB_TOKEN)
                with DataHubContext(client):
                    from datahub_agent_context.mcp_tools import remove_tags
                    remove_tags(
                        tag_urns=[
                            "urn:li:tag:pending-review",
                            "urn:li:tag:pending-review-breaking",
                            "urn:li:tag:pending-review-critical",
                        ],
                        entity_urns=[manual_dataset_urn],
                    )
                st.success("Tags cleared!")
            except Exception as e:
                st.error(f"Could not remove: {e}")

sql_input = st.text_area(
    "SQL Migration",
    height=160,
    value="""ALTER TABLE orders
  DROP COLUMN shipping_address,
  ADD COLUMN loyalty_points INT;

ALTER TABLE customers
  ALTER COLUMN total_amount TYPE DECIMAL(10,2);""",
    help="Paste one or more statements, semicolon-separated. Every table "
         "touched is detected and analyzed automatically."
)

# --- Analysis button ---
analyze_clicked = st.button("🔍 Check Impact", type="primary", use_container_width=True)

if analyze_clicked:
    if not sql_input.strip():
        st.error("Please paste a SQL migration first.")
        st.stop()

    # Parse first (no DataHub call needed) -- returns one entry PER TABLE
    try:
        table_results = parse_multi_table_migration(sql_input)
    except Exception as e:
        st.error(f"Could not parse SQL: {e}")
        st.stop()

    if not table_results:
        st.error("No recognizable table-level operations found in this SQL. Nothing to check.")
        st.stop()

    st.markdown("---")
    st.markdown(f"### Detected **{len(table_results)}** table(s) in this migration")

    per_table_data = {}

    spinner_msg = f"Analyzing {len(table_results)} table(s) against DataHub" + (" (using LLM for explanations)..." if use_llm else "...")
    with st.spinner(spinner_msg):
        try:
            client = DataHubClient(server="http://localhost:8081", token=DATAHUB_TOKEN)
            for parsed in table_results:
                table_name = parsed["table"]
                operations = parsed["operations"]
                dataset_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table_name},PROD)"

                with DataHubContext(client):
                    downstream_assets, lineage_edges = get_multi_hop_downstream(
                        dataset_urn, max_hops=int(max_hops_input)
                    )

                    report = build_full_report(
                        table=table_name,
                        table_urn=dataset_urn,
                        operations=operations,
                        use_llm=use_llm,
                        downstream_assets=downstream_assets,
                    )

                downstream_count = len(downstream_assets)
                downstream_lookup = {
                    op.get("column"): downstream_count
                    for op in operations if op.get("column")
                }
                pii_lookup = {op.get("column"): False for op in operations if op.get("column")}
                classified = classify_migration(operations, downstream_lookup, pii_lookup)
                overall = compute_overall_severity(classified)

                # Automatic tag write-back: fires here (inside the analysis
                # loop) rather than behind a manual button, so it happens
                # exactly once per "Check Impact" click when dry_run is off
                # -- not on every rerun caused by the table selector or
                # other widgets, since this block only runs when
                # analyze_clicked is True. Reuses the same `client` /
                # DataHubContext already open above for this table.
                tag_write_result = None
                if not dry_run:
                    with DataHubContext(client):
                        try:
                            tag_write_result = write_back_tag(
                                dataset_urn, overall, dry_run=False,
                                server="http://localhost:8081", token=DATAHUB_TOKEN
                            )
                        except Exception as e:
                            tag_write_result = {"success": False, "message": str(e)}

                per_table_data[table_name] = {
                    "table_name": table_name,
                    "operations": operations,
                    "dataset_urn": dataset_urn,
                    "downstream_assets": downstream_assets,
                    "lineage_edges": lineage_edges,
                    "report": report,
                    "classified": classified,
                    "overall": overall,
                    "tag_write_result": tag_write_result,
                }
        except Exception as e:
            st.error(f"DataHub connection failed: {e}")
            st.info("Make sure DataHub is running: `datahub docker quickstart`")
            st.stop()

    # Automatic Context Document write-back -- same reasoning as tags above:
    # fires once here, inside `if analyze_clicked:`, not behind a button.
    # Single table -> one document via the original write_back_context_document().
    # Multiple tables -> one COMBINED document via write_back_combined_context_document(),
    # since a migration touching several tables reads better as one linked
    # record than N disconnected ones.
    context_doc_result = None
    context_doc_mode = None
    if save_context_doc and not dry_run:
        with DataHubContext(client):
            try:
                if len(per_table_data) == 1:
                    only = next(iter(per_table_data.values()))
                    context_doc_result = write_back_context_document(
                        table=only["table_name"],
                        table_urn=only["dataset_urn"],
                        report_content=only["report"],
                        overall_severity=only["overall"],
                        dry_run=False,
                    )
                    context_doc_mode = "single"
                else:
                    tables_payload = [
                        {
                            "table": d["table_name"],
                            "table_urn": d["dataset_urn"],
                            "report_content": d["report"],
                            "overall_severity": d["overall"],
                        }
                        for d in per_table_data.values()
                    ]
                    context_doc_result = write_back_combined_context_document(
                        tables_payload, dry_run=False,
                    )
                    context_doc_mode = "combined"
            except Exception as e:
                context_doc_result = {"success": False, "message": str(e)}
                context_doc_mode = "error"

    st.session_state["koza_context_doc_result"] = context_doc_result
    st.session_state["koza_context_doc_mode"] = context_doc_mode

    # Persist results in session_state so they survive reruns triggered by
    # OTHER widgets (the table selector, write-back buttons below). Without
    # this, changing the dropdown would trigger a full script rerun where
    # analyze_clicked is False again -- st.button() only returns True on the
    # exact run it was clicked -- wiping out everything inside this `if`
    # block and forcing the user back to square one.
    st.session_state["koza_per_table_data"] = per_table_data

# Render results from session_state if we have any -- from THIS run's
# button click, or persisted from a prior run. Deliberately OUTSIDE
# `if analyze_clicked:` so switching the table selector below (which
# reruns the whole script) keeps showing results instead of vanishing.
if st.session_state.get("koza_per_table_data"):
    per_table_data = st.session_state["koza_per_table_data"]

    # Overall-of-overalls badge across every table in this migration
    combined_overall = compute_overall_severity(
        [{"severity": d["overall"]} for d in per_table_data.values()]
    )
    color_map = {
        "Safe": ("#28a745", "✅"),
        "Low": ("#ffc107", "⚠️"),
        "Breaking": ("#dc3545", "🚨"),
        "Critical": ("#721c24", "⛔")
    }
    combined_color, combined_icon = color_map.get(combined_overall, ("#6c757d", "❓"))
    st.markdown(
        f"<div style='background-color:{combined_color};padding:12px 20px;border-radius:8px;color:white;font-size:20px;font-weight:bold;'>"
        f"{combined_icon} Highest severity across this migration: {combined_overall}</div>",
        unsafe_allow_html=True
    )
    if use_llm:
        st.caption("✨ Explanations below generated by LLM (Groq) where available, with automatic fallback to the template.")

    # --- Context Document status (automatic, whole-migration) ---
    # The actual save already happened above, inside `if analyze_clicked:`,
    # so this block only DISPLAYS the result -- it never writes anything
    # itself. That's what keeps it safe to sit here, outside
    # `if analyze_clicked:`: dropdown reruns re-render this status line but
    # never re-trigger a save, since st.session_state["koza_context_doc_result"]
    # is only ever set from inside the analysis block.
    if save_context_doc:
        st.markdown("---")
        if dry_run:
            st.info("🔒 **Dry run mode is ON.** No Context Document was saved. Uncheck 'Dry run' in the sidebar and re-run 'Check Impact' to save for real.")
        else:
            doc_result = st.session_state.get("koza_context_doc_result")
            doc_mode = st.session_state.get("koza_context_doc_mode")
            if doc_result is None:
                st.info("Context Document saving is enabled -- click 'Check Impact' again to generate and save it for this migration.")
            elif doc_result.get("success"):
                doc_urn = doc_result.get("urn", "")
                if doc_mode == "combined":
                    st.success(f"✅ Combined Context Document saved for all {len(per_table_data)} tables: `{doc_result.get('message')}`")
                else:
                    st.success(f"✅ Context Document saved: `{doc_result.get('message')}`")
                if doc_urn:
                    st.info(f"View it at: http://localhost:9002/document/{doc_urn}")
            else:
                st.error(f"Context Document write failed: {doc_result}")

    # --- Table selector (NOT st.tabs) ---
    # Deliberately using a selectbox instead of st.tabs here: st.tabs renders
    # every tab's content into the page at once (inactive tabs are only
    # hidden via CSS, not skipped), and Mermaid cannot compute an SVG's
    # layout inside a hidden container -- so any tab other than the first
    # would silently fail to render its diagram. A selectbox makes Streamlit
    # create the component ONLY for the currently-selected table, so its
    # Mermaid iframe is never hidden at load time and always renders.
    #
    # Explicit `key` so Streamlit tracks this widget's state independently
    # of the surrounding layout -- keeps the selection stable across reruns
    # triggered by other widgets on the page (e.g. the sidebar checkboxes).
    st.markdown("#### Select a table to view")
    table_names = list(per_table_data.keys())
    selected_table = st.selectbox(
        "Table",
        options=table_names,
        format_func=lambda name: f"{color_map.get(per_table_data[name]['overall'], ('', '❓'))[1]} {name} ({per_table_data[name]['overall']})",
        label_visibility="collapsed",
        key="koza_table_selector",
    )

    # Quick-glance strip of every table's severity, so switching the
    # selector isn't the only way to see the overall picture at once.
    overview_cols = st.columns(len(table_names))
    for col, name in zip(overview_cols, table_names):
        sev = per_table_data[name]["overall"]
        sev_color, sev_icon = color_map.get(sev, ("#6c757d", "❓"))
        with col:
            st.markdown(
                f"<div style='text-align:center;padding:6px;border-radius:6px;"
                f"background-color:{sev_color}22;border:1px solid {sev_color};'>"
                f"<b>{sev_icon} {name}</b><br/><span style='color:{sev_color};'>{sev}</span></div>",
                unsafe_allow_html=True
            )

    d = per_table_data[selected_table]
    table_name = selected_table
    with st.container():
        color, icon = color_map.get(d["overall"], ("#6c757d", "❓"))
        st.markdown(
            f"<div style='background-color:{color};padding:8px 16px;border-radius:8px;color:white;font-weight:bold;'>"
            f"{icon} `{table_name}` — Severity: {d['overall']}</div>",
            unsafe_allow_html=True
        )

        st.markdown("#### Per-Column Verdict")
        classified = d["classified"]
        if classified:
            cols = st.columns(len(classified))
            for i, c in enumerate(classified):
                with cols[i]:
                    sev = c["severity"]
                    sev_color = color_map.get(sev, ("#6c757d", "?"))[0]
                    st.markdown(
                        f"<div style='border-left:4px solid {sev_color};padding-left:10px;'>"
                        f"<b>{c['column']}</b><br/><span style='color:{sev_color};font-weight:bold;'>{sev}</span></div>",
                        unsafe_allow_html=True
                    )

        st.markdown("#### Impact Report")
        st.markdown(d["report"])

        st.markdown("#### Downstream Lineage")
        chains_text = format_lineage_chains(table_name, d["dataset_urn"], d["lineage_edges"])
        st.text(chains_text)
        render_mermaid(build_mermaid_graph(table_name, d["downstream_assets"]))

        if show_details:
            with st.expander("Raw technical output"):
                st.json({
                    "parsed_operations": d["operations"],
                    "downstream_count": len(d["downstream_assets"]),
                    "downstream_assets": d["downstream_assets"],
                    "lineage_edges": d["lineage_edges"],
                    "classified": d["classified"],
                    "overall": d["overall"],
                    "dataset_urn": d["dataset_urn"],
                })

        st.markdown("---")
        st.markdown("#### Write-back to DataHub")
        if dry_run:
            st.info("🔒 **Dry run mode is ON.** Nothing was written to DataHub. Uncheck 'Dry run' in the sidebar and re-run 'Check Impact' to write for real.")
        else:
            # Tag write already happened automatically during analysis
            # above (inside `if analyze_clicked:`) -- this only displays
            # that result, it never writes anything itself. That's what
            # keeps this safe to re-render on every table-selector rerun
            # without duplicating writes.
            tag_result = d.get("tag_write_result")
            if tag_result is None:
                st.info(f"Severity '{d['overall']}' is below the tagging threshold -- no tag written for `{table_name}`.")
            elif tag_result.get("success"):
                st.success(f"✅ Tag written for `{table_name}`: `{tag_result.get('message')}`")
                st.info(f"View it at: http://localhost:9002/dataset/{d['dataset_urn']}")
            else:
                st.error(f"Tag write failed for `{table_name}`: {tag_result}")

            # Opt-in: save THIS table's report as its own separate Context
            # Document, in addition to the automatic combined one above.
            # Only offered for multi-table migrations -- for a single-table
            # migration the automatic save above already IS this table's
            # document, so a duplicate button here would just create a
            # redundant second copy. Stays a manual button (unlike tags and
            # the combined doc) since it's an extra, optional artifact the
            # user has to actively want, not something that should fire on
            # every analysis run.
            if save_context_doc and len(per_table_data) > 1:
                save_sep_clicked = st.button(
                    f"💾 Also save '{table_name}' as a separate Context Document",
                    key=f"save_sep_doc_{table_name}",
                )
                if save_sep_clicked:
                    sep_client = DataHubClient(server="http://localhost:8081", token=DATAHUB_TOKEN)
                    with DataHubContext(sep_client):
                        with st.spinner(f"Saving separate Context Document for `{table_name}`..."):
                            try:
                                sep_result = write_back_context_document(
                                    table=table_name,
                                    table_urn=d["dataset_urn"],
                                    report_content=d["report"],
                                    overall_severity=d["overall"],
                                    dry_run=False,
                                )
                                if sep_result and sep_result.get("success"):
                                    sep_urn = sep_result.get("urn", "")
                                    st.success(f"✅ Separate Context Document saved for `{table_name}`: `{sep_result.get('message')}`")
                                    if sep_urn:
                                        st.info(f"View it at: http://localhost:9002/document/{sep_urn}")
                                else:
                                    st.error(f"Separate Context Document write failed for `{table_name}`: {sep_result}")
                            except Exception as e:
                                st.error(f"Separate Context Document write-back failed for `{table_name}`: {e}")

# --- Footer ---
st.markdown("---")
st.caption("koza--PR Impact Guardian | DataHub Agent Hackathon 2026")
