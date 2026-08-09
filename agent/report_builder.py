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

MULTI-HOP ADDITION: get_multi_hop_downstream() and format_lineage_chains()
below are new and purely additive -- get_downstream_assets() itself is
UNCHANGED. The 1-hop limit lives inside the third-party
datahub_agent_context.mcp_tools.get_lineage() call, which is not safe to
edit (it would be wiped on package reinstall). Instead, get_multi_hop_downstream()
calls the existing get_downstream_assets() repeatedly -- hop-1 results
become the new starting points for hop-2, and so on -- so multi-hop
lineage ("A affects B affects C") is achieved with zero third-party code
touched and 100% reuse of what's already tested.
"""

from typing import List, Dict, Any, Optional, Tuple

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
    """UNCHANGED -- the already-tested 1-hop lineage lookup. Everything new
    below builds on top of this without modifying it."""
    from datahub_agent_context.mcp_tools import get_lineage
    lineage = get_lineage(urn=table_urn, upstream=False)
    results = _extract_downstream_results(lineage)
    assets = []
    for r in results:
        entity = r.get("entity", {}) or {}
        assets.append({
            "name": entity.get("name") or entity.get("urn", "unknown"),
            "type": entity.get("type", "unknown"),
            "urn": entity.get("urn"),
        })
    return assets


def get_multi_hop_downstream(
    table_urn: str, max_hops: int = 2
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, int]]]:
    """
    Traverses downstream lineage beyond the direct 1-hop dependents that
    get_downstream_assets() returns on its own, by calling it repeatedly:
    hop-1 results become the new starting points for hop-2, and so on, up
    to max_hops. Breadth-first, deduplicated by URN so diamond-shaped
    lineage (two paths converging on the same asset) isn't double-counted
    or looped forever.

    Must be called from inside an active DataHubContext, same as
    get_downstream_assets() itself.

    Returns:
        (all_assets, edges)
        all_assets: flat list of every unique downstream asset dict found
            within max_hops (same shape as get_downstream_assets() returns,
            now including "urn" so this traversal and format_lineage_chains()
            below can work with it).
        edges: list of (from_urn, to_urn, hop_number) tuples -- lets a
            caller reconstruct and display actual chains, e.g.
            "orders -> customer_summary_dashboard -> exec_kpi_rollup".
    """
    visited = {table_urn}
    frontier = [table_urn]
    all_assets: Dict[str, Dict[str, Any]] = {}
    edges: List[Tuple[str, str, int]] = []

    for hop in range(1, max_hops + 1):
        next_frontier = []
        for urn in frontier:
            try:
                assets = get_downstream_assets(urn)
            except Exception:
                assets = []
            for asset in assets:
                asset_urn = asset.get("urn")
                edges.append((urn, asset_urn, hop))
                if asset_urn and asset_urn not in visited:
                    visited.add(asset_urn)
                    all_assets[asset_urn] = asset
                    next_frontier.append(asset_urn)
        frontier = next_frontier
        if not frontier:
            break

    return list(all_assets.values()), edges


def _urn_short_name(urn: Optional[str]) -> str:
    """Best-effort: pull a readable name out of a DataHub dataset URN."""
    if not urn:
        return "unknown"
    if "," in urn:
        parts = urn.split(",")
        if len(parts) >= 2:
            return parts[1]
    return urn


def format_lineage_chains(
    root_name: str, root_urn: str, edges: List[Tuple[str, str, int]]
) -> str:
    """
    Turns the raw (from_urn, to_urn, hop) edges from get_multi_hop_downstream()
    into a human-readable "A -> B -> C" chain listing, one line per unique
    path. root_urn is passed in explicitly by the caller (get_multi_hop_downstream()
    always starts from it) rather than guessed from the edges list -- guessing
    is unnecessary and fragile when the caller already knows the answer.

    Falls back to a "no downstream dependents" message if there are no edges.
    """
    if not edges:
        return f"{root_name}: no downstream dependents found."

    children: Dict[str, List[str]] = {}
    for from_urn, to_urn, _hop in edges:
        children.setdefault(from_urn, []).append(to_urn)

    lines: List[str] = []

    def walk(urn: str, path: List[str], depth: int):
        kids = children.get(urn, [])
        if not kids or depth >= 4:  # hard safety cap against pathological cycles
            lines.append(" -> ".join(path))
            return
        for kid in kids:
            walk(kid, path + [_urn_short_name(kid)], depth + 1)

    walk(root_urn, [root_name], 1)
    return "\n".join(lines)


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

    sections = [f"# koza Impact Report: `{table}`\n"]
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
