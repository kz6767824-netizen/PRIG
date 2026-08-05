"""
report_builder.py

HYBRID FORMAT (unchanged from your version):
  1. Overall severity badge + summary table at top
  2. Per-column detailed explanations (template or LLM)
  3. Optional safe migration patch for Breaking/Critical
  4. Standing disclaimer

FIX: build_full_report() now accepts an optional `downstream_assets`
parameter. If provided, it's used as-is and NO live DataHub call is made
inside this function. If omitted (None), it fetches live, same as before --
so app.py's existing calls (which don't pass it) are unaffected.

This fixes a real bug: interactive_agent.py fetches downstream_assets ONCE
inside its own DataHubContext at session startup, then exits that context
before entering the interactive command loop. Without this fix, typing
'report' later calls build_full_report(), which would try to query DataHub
AGAIN -- outside any active context -- and crash with "No DataHubClient in
context", the same bug class already hit and fixed in app.py earlier in
this project.
"""

from typing import List, Dict, Any, Optional

from severity import classify_migration
from severity_rollup import compute_overall_severity
from explainer import template_explanation
from rename_heuristic import rename_note

DISCLAIMER = (
    "\n\n---\n\n"
    "**Note:** These suggestions reflect general best-practice patterns and do "
    "not account for your team's specific constraints, release cycle, "
    "compliance deadlines, or urgency. A human reviewer should confirm this "
    "approach fits the actual situation before merging.\n\n"
    "Severity classification is fully deterministic and reproducible. If an "
    "LLM-generated explanation is used instead of the template, its exact "
    "wording may vary slightly between runs on the same input — the "
    "severity label itself will not.\n\n"
    "PII detection: this version does not attempt automatic column-level PII "
    "detection. Live testing confirmed the tag WRITE path works (add_tags with "
    "column_paths), but no read path currently available through the Agent "
    "Context Kit tools surfaces column-level tags back. See README for detail."
)


def _extract_downstream_results(lineage_response: Any) -> List[Dict[str, Any]]:
    if not lineage_response or not isinstance(lineage_response, dict):
        return []
    downstreams = lineage_response.get("downstreams")
    if not downstreams or not isinstance(downstreams, dict):
        return []
    return downstreams.get("searchResults", []) or []


def get_downstream_assets(table_urn: str) -> List[Dict[str, Any]]:
    from datahub_agent_context.mcp_tools import get_lineage
    lineage = get_lineage(urn=table_urn, upstream=False)
    results = _extract_downstream_results(lineage)
    assets = []
    for r in results:
        entity = r.get("entity", {}) or {}
        assets.append({
            "name": entity.get("name") or entity.get("urn", "unknown"),
            "type": entity.get("type", "unknown"),
        })
    return assets


def get_pii_flag_for_column(table_urn: str, column: str) -> bool:
    return False


def build_lookups(table_urn, operations, downstream_assets):
    downstream_count = len(downstream_assets)
    downstream_lookup = {}
    pii_lookup = {}
    for op in operations:
        column = op.get("column")
        if not column:
            continue
        downstream_lookup[column] = downstream_count
        pii_lookup[column] = get_pii_flag_for_column(table_urn, column)
    return downstream_lookup, pii_lookup


def build_full_report(
    table: str,
    table_urn: str,
    operations: List[Dict[str, Any]],
    use_llm: bool = False,
    downstream_assets: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    downstream_assets: if provided, used as-is (NO live DataHub call made
        here). If None (default), fetched live via get_downstream_assets().
        Pass a pre-fetched list when calling this OUTSIDE an active
        DataHubContext (e.g. interactive_agent.py's command loop).
    """
    if downstream_assets is None:
        downstream_assets = get_downstream_assets(table_urn)

    downstream_lookup, pii_lookup = build_lookups(table_urn, operations, downstream_assets)
    classified = classify_migration(operations, downstream_lookup, pii_lookup)
    overall = compute_overall_severity(classified)

    sections = [f"# PR Impact Report: `{table}`\n"]
    sections.append(f"**Overall Severity:** `{overall}`\n")

    sections.append("### Summary\n")
    sections.append("| Operation | Column | Severity | Downstream Count |")
    sections.append("|---|---|---|---|")
    for item in classified:
        col = item.get("column", "N/A")
        count = downstream_lookup.get(col, len(downstream_assets)) if col != "N/A" else len(downstream_assets)
        sections.append(f"| {item['action']} | `{col}` | **{item['severity']}** | {count} |")
    sections.append("")

    note = rename_note(operations)
    if note:
        sections.append(f"> {note}\n")

    for result in classified:
        column = result["column"]
        is_pii = pii_lookup.get(column, False) if column else False

        if use_llm:
            from llm_explanation import llm_explanation
            explanation = llm_explanation(
                table=table, column=column, operation=result["action"],
                severity=result["severity"], downstream_assets=downstream_assets,
                is_pii=is_pii, governance_flags=result.get("governance_flags", []),
                new_column=result.get("new_column"),
            )
        else:
            explanation = template_explanation(
                table=table, operations=[result["action"]], severity=result["severity"],
                downstream_assets=downstream_assets, is_pii=is_pii,
                governance_flags=result.get("governance_flags", []),
                new_column=result.get("new_column"), column=column,
            )
        header = f"`{column}`" if column else "table-level"
        sections.append(f"## Column: {header}\n{explanation}\n")

    if overall in ("Breaking", "Critical"):
        from patch_generator import generate_sql_patch
        try:
            patch_sql = generate_sql_patch(table, operations)
            if patch_sql:
                sections.append("## Suggested Safe Migration Patch\n")
                sections.append("```sql\n" + patch_sql + "\n```\n")
        except Exception:
            pass

    sections.append(DISCLAIMER)
    return "\n".join(sections)