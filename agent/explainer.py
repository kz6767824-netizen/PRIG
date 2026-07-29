"""
explainer.py

template_explanation() is now called ONCE PER OPERATION (per column) by
report_builder.py, rather than once for a whole migration. The function
body barely changes from the original — it already accepted a single
`operations` list and worked fine when that list happened to contain one
item. The additions here are:
  - a `governance_flags` param, so PII-on-ADD can be surfaced even when
    severity stays "Safe"
  - minor wording tweaks since `operations` will now realistically always
    be a length-1 list (e.g. ["DROP"]) rather than a mixed migration-wide list
"""

from typing import List, Dict, Any, Optional


def template_explanation(
    table: str,
    operations: List[str],
    severity: str,
    downstream_assets: List[Dict[str, Any]],
    is_pii: bool = False,
    governance_flags: Optional[List[str]] = None,
) -> str:
    """
    Generates a structured explanation for a SINGLE operation using
    real DataHub-derived factors: operation type, severity, downstream
    asset types/count, and PII flag.
    """
    governance_flags = governance_flags or []

    has_add = "ADD" in operations
    has_drop = "DROP" in operations
    has_type_change = "TYPE_CHANGE" in operations
    has_rename = "RENAME" in operations
    has_set_not_null = "SET_NOT_NULL" in operations

    dashboards = [a for a in downstream_assets if a.get("type", "").upper() == "DASHBOARD"]
    asset_names = [a["name"] for a in downstream_assets]

    lines = []
    lines.append(f"Table: {table}")
    lines.append(f"Severity: {severity}")
    lines.append("")

    # --- Downstream summary, DataHub-aware ---
    if downstream_assets:
        lines.append(f"Downstream impact ({len(downstream_assets)} asset(s)):")
        for a in downstream_assets:
            lines.append(f"  - {a['name']} ({a.get('type', 'unknown').lower()})")
        if dashboards:
            lines.append(
                f"  Note: {len(dashboards)} of these are dashboards — changes here "
                f"are directly user-facing, not just internal pipeline data."
            )
    else:
        lines.append("Downstream impact: none found in DataHub's lineage graph.")
    lines.append("")

    # --- Suggestion, branching on operation type + severity + asset count ---
    if has_rename:
        lines.append(
            "Suggested action: This is an explicit column rename. Downstream "
            "consumers referencing the old column name will break even though "
            "the underlying data is preserved. Update references before or "
            "alongside merging this change."
        )
    elif has_set_not_null:
        lines.append(
            "Suggested action: Adding NOT NULL to an existing column fails on "
            "any existing NULL rows. Backfill a value for all existing rows "
            "before applying the constraint, or add the constraint at the "
            "application layer first as a soft check."
        )
    elif has_type_change:
        lines.append(
            "Suggested action: Type changes can silently corrupt downstream "
            "calculations even when they look compatible. Consider adding a new "
            "column with the target type, backfilling it, and migrating "
            "downstream consumers before removing the original column."
        )
    elif has_drop:
        if severity in ("Breaking", "Critical"):
            if len(downstream_assets) > 2:
                lines.append(
                    f"Suggested action: This column feeds {len(downstream_assets)} "
                    "downstream assets — a direct drop is high-risk. Recommend a "
                    "phased deprecation: keep the column live, mark it deprecated "
                    "in DataHub's description, and set a removal date only after "
                    "confirming all consumers have migrated."
                )
            else:
                lines.append(
                    "Suggested action: Coordinate directly with the owner(s) of "
                    "the affected downstream asset(s) before merging. A short "
                    "deprecation window (even a few days) reduces risk "
                    "significantly compared to an immediate drop."
                )
        else:
            lines.append(
                "Suggested action: No downstream dependents were found in "
                "DataHub's lineage graph. This appears safe to proceed, but "
                "double-check that lineage is fully up to date — unregistered "
                "or undocumented consumers wouldn't show up here."
            )
    elif has_add:
        lines.append(
            "Suggested action: Additive changes are generally safe. No action "
            "needed beyond normal review."
        )
    else:
        lines.append("Suggested action: No specific recommendation — review manually.")

    # --- PII/compliance note, DataHub-tag-derived ---
    if is_pii:
        lines.append("")
        lines.append(
            "Compliance note: This column is tagged as PII/sensitive in DataHub. "
            "Any change here may have governance or compliance implications "
            "beyond technical breakage — consider looping in your data "
            "governance owner before merging."
        )

    # --- Governance flags (can apply even when severity is Safe) ---
    if "NEW_PII_COLUMN_ADDED" in governance_flags:
        lines.append("")
        lines.append(
            "Governance note: This adds a NEW PII-tagged column. Even though "
            "this is not a breaking change, confirm appropriate masking/access "
            "controls are applied before merging."
        )

    return "\n".join(lines)


if __name__ == "__main__":
    downstream_example = [
        {"name": "daily_revenue", "type": "DATASET"},
        {"name": "executive_dashboard", "type": "DASHBOARD"},
        {"name": "customer_shipping_report", "type": "DATASET"},
    ]
    print(template_explanation(
        table="orders",
        operations=["DROP"],
        severity="Breaking",
        downstream_assets=downstream_example,
        is_pii=False,
    ))
