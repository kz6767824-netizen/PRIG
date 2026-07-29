import streamlit as st
import sys
import os

# Add agent folder to Python path
AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent")
sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from parse_migration import parse_migration
from report_builder import build_full_report
from severity import classify_migration
from severity_rollup import compute_overall_severity
from write_back_tag import write_back_tag

st.set_page_config(page_title="PR Impact Guardian", layout="centered")
st.title("🛡️ PR Impact Guardian")
st.caption("One bad ALTER TABLE can silently break every downstream dashboard.Don't let a DROP COLUMN become a production incident. This agent stops it before merge.")

# --- Sidebar controls ---
st.sidebar.header("Settings")
dry_run = st.sidebar.checkbox("🔒 Dry run (don't write to DataHub)", value=True)
show_details = st.sidebar.checkbox("Show technical details", value=False)

st.sidebar.markdown("---")
st.sidebar.markdown("**How it works:**")
st.sidebar.markdown("""
1. Paste your SQL migration
2. We parse it and check DataHub's real schema + lineage
3. You get a severity verdict and impact report
4. If not dry-run, we tag the dataset in DataHub
""")

# --- Main form ---
st.markdown("### Migration Input")

table_name = st.text_input("Table name", value="orders", help="The table this migration targets")

sql_input = st.text_area(
    "SQL Migration",
    height=120,
    value="""ALTER TABLE orders
  DROP COLUMN shipping_address,
  ADD COLUMN loyalty_points INT;""",
    help="Paste a single ALTER TABLE statement"
)

# --- Analysis button ---
analyze_clicked = st.button("🔍 Check Impact", type="primary", use_container_width=True)

if analyze_clicked:
    if not sql_input.strip():
        st.error("Please paste a SQL migration first.")
        st.stop()

    # Parse first (no DataHub call needed)
    try:
        parsed = parse_migration(sql_input)
        if parsed.get("table") != table_name:
            st.warning(f"Parser detected table `{parsed.get('table')}`, but you entered `{table_name}`. Using parsed table name.")
            table_name = parsed.get("table")
    except Exception as e:
        st.error(f"Could not parse SQL: {e}")
        st.stop()

    dataset_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table_name},PROD)"

    with st.spinner("Analyzing against DataHub..."):
        try:
            client = DataHubClient(server="http://localhost:8081", token="")
            with DataHubContext(client):
                # Build report (includes live lineage + severity per operation)
                report = build_full_report(
                    table=table_name,
                    table_urn=dataset_urn,
                    operations=parsed["operations"],
                )

                # Recompute classified operations for the rollup
                from report_builder import get_downstream_assets
                downstream_assets = get_downstream_assets(dataset_urn)
                downstream_count = len(downstream_assets)
                downstream_lookup = {
                    op.get("column"): downstream_count 
                    for op in parsed["operations"] if op.get("column")
                }
                pii_lookup = {op.get("column"): False for op in parsed["operations"] if op.get("column")}

                classified = classify_migration(parsed["operations"], downstream_lookup, pii_lookup)
                overall = compute_overall_severity(classified)

        except Exception as e:
            st.error(f"DataHub connection failed: {e}")
            st.info("Make sure DataHub is running: `datahub docker quickstart`")
            st.stop()

    # --- Display results ---
    st.markdown("---")
    
    # Severity badge
    color_map = {
        "Safe": ("#28a745", "✅"),
        "Low": ("#ffc107", "⚠️"),
        "Breaking": ("#dc3545", "🚨"),
        "Critical": ("#721c24", "⛔")
    }
    color, icon = color_map.get(overall, ("#6c757d", "❓"))
    
    st.markdown(
        f"<div style='background-color:{color};padding:12px 20px;border-radius:8px;color:white;font-size:20px;font-weight:bold;'>"
        f"{icon} Overall Severity: {overall}</div>",
        unsafe_allow_html=True
    )

    # Per-operation breakdown
    st.markdown("### Per-Column Verdict")
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

    # Full report
    st.markdown("### Impact Report")
    st.markdown(report)

    # Technical details (collapsible)
    if show_details:
        with st.expander("Raw technical output"):
            st.json({
                "parsed_operations": parsed["operations"],
                "downstream_count": downstream_count,
                "downstream_assets": downstream_assets,
                "classified": classified,
                "overall": overall,
                "dataset_urn": dataset_urn,
            })

    # Write-back section
    st.markdown("---")
    if dry_run:
        st.info("🔒 **Dry run mode is ON.** No tag was written to DataHub. Uncheck 'Dry run' in the sidebar and re-run to write the tag.")
    else:
        with st.spinner("Writing tag to DataHub..."):
            try:
                result = write_back_tag(dataset_urn, overall, dry_run=False)
                if result.get("success"):
                    st.success(f"✅ Tag written to DataHub: `{result.get('message')}`")
                    st.info(f"View it at: http://localhost:9002/dataset/{dataset_urn}")
                else:
                    st.error(f"Write failed: {result}")
            except Exception as e:
                st.error(f"Write-back failed: {e}")

# --- Footer ---
st.markdown("---")
st.caption("PR Impact Guardian | DataHub Agent Hackathon 2026")