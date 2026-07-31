"""
explainer.py

FIXES applied:
  1. Added an explicit DROP_TABLE/TRUNCATE branch.
  2. RENAME's suggestion text now references new_column.
  3. All headers now use Markdown bullet points so they render on separate lines.
  4. Every suggestion block starts with a bold **Suggestion:** heading.
  5. Wording acknowledges that dependencies have ALREADY been checked by the tool.
  6. Disclaimer is appended separately by report_builder.py, not inside this function.
"""

from typing import List, Dict, Any, Optional


def template_explanation(
    table: str,
    operations: List[str],
    severity: str,
    downstream_assets: List[Dict[str, Any]],
    is_pii: bool = False,
    governance_flags: Optional[List[str]] = None,
    new_column: Optional[str] = None,
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
    has_table_drop = "DROP_TABLE" in operations
    has_truncate = "TRUNCATE" in operations

    dashboards = [a for a in downstream_assets if a.get("type", "").upper() == "DASHBOARD"]
    asset_names = [a["name"] for a in downstream_assets]

    lines = []
    # FIX: Use Markdown bullet points so each renders on its own line
    lines.append(f"- **Table:** `{table}`")
    lines.append(f"- **Severity:** `{severity}`")
    lines.append("")

    # --- Downstream summary ---
    if downstream_assets:
        lines.append(f"**Downstream impact:** {len(downstream_assets)} asset(s) found in DataHub:")
        for a in downstream_assets:
            lines.append(f"  - `{a['name']}` ({a.get('type', 'unknown').lower()})")
        if dashboards:
            lines.append(
                f"  - **Note:** {len(dashboards)} of these are dashboards — "
                f"changes here are directly user-facing."
            )
    else:
        lines.append("**Downstream impact:** None found in DataHub's lineage graph.")
    lines.append("")

    # --- Suggestion, branching on operation type ---
    if has_table_drop or has_truncate:
        action_word = "drop" if has_table_drop else "truncate"
        lines.append("**Suggestion:**")
        lines.append(
            f"This permanently {action_word}s the entire table and ALL of its data. "
            f"The affected downstream assets are listed above. Get explicit "
            f"confirmation from every downstream owner before proceeding, and "
            f"verify a backup or rollback plan exists first."
        )
    elif has_rename:
        target_desc = f" to `{new_column}`" if new_column else ""
        lines.append("**Suggestion:**")
        lines.append(
            f"This is an explicit column rename{target_desc}. The affected "
            f"downstream asset(s) are listed above — update any references to "
            f"the old column name before or alongside merging this change."
        )
    elif has_set_not_null:
        lines.append("**Suggestion:**")
        lines.append(
            "Adding NOT NULL to an existing column fails on any existing NULL "
            "rows. Backfill a value for all existing rows before applying the "
            "constraint, or add the constraint at the application layer first "
            "as a soft check."
        )
    elif has_type_change:
        lines.append("**Suggestion:**")
        lines.append(
            "Dependencies already checked (see above). Type changes can silently "
            "corrupt downstream calculations. Consider adding a new column with "
            "the target type, backfilling it, and migrating downstream consumers "
            "before removing the original column."
        )
    elif has_drop:
        if severity in ("Breaking", "Critical"):
            asset_list = ", ".join(f"`{a['name']}`" for a in downstream_assets)
            if len(downstream_assets) > 2:
                lines.append("**Suggestion:**")
                lines.append(
                    f"Dependencies already checked — this column feeds "
                    f"{len(downstream_assets)} downstream assets (listed above). "
                    f"Do not drop directly. Use a phased deprecation: keep the "
                    f"column live, mark it deprecated in DataHub, and remove it "
                    f"only after confirming all consumers have migrated."
                )
            else:
                lines.append("**Suggestion:**")
                lines.append(
                    f"Dependencies already checked — affected downstream asset(s): "
                    f"{asset_list}. Coordinate with the owner(s) of these asset(s) "
                    f"before merging. A short deprecation window reduces risk "
                    f"compared to an immediate drop."
                )
        else:
            lines.append("**Suggestion:**")
            lines.append(
                "No downstream dependents were found in DataHub's lineage graph. "
                "This appears safe to proceed, but double-check that lineage is "
                "fully up to date — unregistered consumers wouldn't show up here."
            )
    elif has_add:
        lines.append("**Suggestion:**")
        lines.append(
            "Additive changes are generally safe. No action needed beyond normal review."
        )
    else:
        lines.append("**Suggestion:**")
        lines.append("No specific recommendation — review manually.")

    # --- PII/compliance note ---
    if is_pii:
        lines.append("")
        lines.append(
            "**Compliance note:** This column is tagged as PII/sensitive in DataHub. "
            "Any change here may have governance or compliance implications "
            "beyond technical breakage — consider looping in your data "
            "governance owner before merging."
        )

    # --- Governance flags ---
    if "NEW_PII_COLUMN_ADDED" in governance_flags:
        lines.append("")
        lines.append(
            "**Governance note:** This adds a NEW PII-tagged column. Even though "
            "this is not a breaking change, confirm appropriate masking/access "
            "controls are applied before merging."
        )

    return "\n".join(lines)


if __name__ == "__main__":
    print("--- Test: DROP_TABLE ---")
    print(template_explanation(
        table="old_staging_table",
        operations=["DROP_TABLE"],
        severity="Critical",
        downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DASHBOARD"}],
    ))
    print("\n--- Test: RENAME with new_column ---")
    print(template_explanation(
        table="orders",
        operations=["RENAME"],
        severity="Breaking",
        downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DATASET"}],
        new_column="delivery_address",
    ))
    print("\n--- Test: DROP with downstream ---")
    print(template_explanation(
        table="orders",
        operations=["DROP"],
        severity="Breaking",
        downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DATASET"}],
    ))