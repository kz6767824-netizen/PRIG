"""
agent/explainer.py

Deterministic template explanations + remediation SQL generator.
"""

from typing import List, Dict, Any, Optional


def generate_remediation_sql(
    table: str,
    operations: List[str],
    column: Optional[str] = None,
    new_column: Optional[str] = None,
) -> str:
    """
    Generates safe, non-breaking SQL refactoring patterns for destructive operations.
    Uses the rename-then-view pattern to avoid duplicate column errors.
    """
    col = column or "<column_name>"
    has_drop = "DROP" in operations
    has_rename = "RENAME" in operations
    has_type_change = "TYPE_CHANGE" in operations
    has_table_drop = "DROP_TABLE" in operations

    if has_table_drop:
        return (
            f"-- Safe deprecation for table drop:\n"
            f"-- Step 1: Rename table to preserve data during transition\n"
            f"ALTER TABLE {table} RENAME TO {table}_deprecated_archive;\n\n"
            f"-- Step 2: Create view with old name for backward compatibility\n"
            f"CREATE OR REPLACE VIEW {table} AS\n"
            f"SELECT * FROM {table}_deprecated_archive;\n\n"
            f"-- Step 3: After confirming zero queries, drop archived table\n"
            f"-- DROP TABLE {table}_deprecated_archive;"
        )

    if has_rename:
        target = new_column or "<new_column_name>"
        return (
            f"-- Safe rename for '{col}' -> '{target}':\n"
            f"-- Step 1: Add new column\n"
            f"ALTER TABLE {table} ADD COLUMN {target} <TYPE>;\n\n"
            f"-- Step 2: Backfill existing data\n"
            f"-- UPDATE {table} SET {target} = {col};\n\n"
            f"-- Step 3: Rename old column to free up the name\n"
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n\n"
            f"-- Step 4: Create view with old name for backward compatibility\n"
            f"CREATE OR REPLACE VIEW {table}_legacy AS\n"
            f"SELECT {col}_deprecated AS {col}, *\n"
            f"FROM {table};\n\n"
            f"-- Step 5: After all consumers migrate, drop deprecated column\n"
            f"-- ALTER TABLE {table} DROP COLUMN {col}_deprecated;"
        )

    if has_type_change:
        return (
            f"-- Safe type change for '{col}':\n"
            f"-- Step 1: Add new column with target type\n"
            f"ALTER TABLE {table} ADD COLUMN {col}_new <TARGET_TYPE>;\n\n"
            f"-- Step 2: Backfill with explicit cast\n"
            f"-- UPDATE {table} SET {col}_new = CAST({col} AS <TARGET_TYPE>);\n\n"
            f"-- Step 3: Rename old column to free up the name\n"
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n\n"
            f"-- Step 4: Create view with old name pointing to new column\n"
            f"CREATE OR REPLACE VIEW {table}_legacy AS\n"
            f"SELECT {col}_new AS {col}, *\n"
            f"FROM {table};\n\n"
            f"-- Step 5: After migration, drop deprecated column\n"
            f"-- ALTER TABLE {table} DROP COLUMN {col}_deprecated;"
        )

    if has_drop:
        return (
            f"-- Safe deprecation for column '{col}':\n"
            f"-- Step 1: Rename column to preserve data and free up the name\n"
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n\n"
            f"-- Step 2: Create backward-compatible view with old column name\n"
            f"CREATE OR REPLACE VIEW {table}_legacy AS\n"
            f"SELECT {col}_deprecated AS {col}, *\n"
            f"FROM {table};\n\n"
            f"-- Step 3: After all consumers migrate, drop deprecated column\n"
            f"-- ALTER TABLE {table} DROP COLUMN {col}_deprecated;"
        )

    return ""


def template_explanation(
    table: str,
    operations: List[str],
    severity: str,
    downstream_assets: List[Dict[str, Any]],
    is_pii: bool = False,
    governance_flags: Optional[List[str]] = None,
    new_column: Optional[str] = None,
    column: Optional[str] = None,
) -> str:
    """
    Generates a structured explanation for a SINGLE operation.
    FIX: `column` moved to the END of the signature to avoid positional-arg mismatch
    with llm_explanation.py's fallback call.
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

    lines = []
    lines.append(f"- **Table:** `{table}`")
    if column:
        lines.append(f"- **Column:** `{column}`")
    lines.append(f"- **Severity:** `{severity}`")
    lines.append("")

    # Downstream summary
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

    # Suggestion
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
            "Type changes can silently corrupt downstream calculations. "
            "Consider adding a new column with the target type, backfilling it, "
            "and migrating downstream consumers before removing the original column."
        )
    elif has_drop:
        if severity in ("Breaking", "Critical"):
            if len(downstream_assets) > 2:
                lines.append("**Suggestion:**")
                lines.append(
                    f"This column feeds {len(downstream_assets)} downstream assets. "
                    f"Do not drop directly. Use a phased deprecation: keep the "
                    f"column live, mark it deprecated in DataHub, and remove it "
                    f"only after confirming all consumers have migrated."
                )
            else:
                lines.append("**Suggestion:**")
                lines.append(
                    "Coordinate directly with the owner(s) of the affected "
                    "downstream asset(s) before merging. A short deprecation "
                    "window reduces risk compared to an immediate drop."
                )
        else:
            lines.append("**Suggestion:**")
            lines.append(
                "No downstream dependents were found. This appears safe, but "
                "double-check that lineage is fully up to date."
            )
    elif has_add:
        lines.append("**Suggestion:**")
        lines.append(
            "Additive changes are generally safe. No action needed beyond normal review."
        )
    else:
        lines.append("**Suggestion:**")
        lines.append("No specific recommendation — review manually.")

    # PII note
    if is_pii:
        lines.append("")
        lines.append(
            "**Compliance note:** This column is tagged as PII/sensitive in DataHub. "
            "Any change here may have governance implications — consider looping in "
            "your data governance owner before merging."
        )

    if "NEW_PII_COLUMN_ADDED" in governance_flags:
        lines.append("")
        lines.append(
            "**Governance note:** This adds a NEW PII-tagged column. Confirm "
            "appropriate masking/access controls are applied before merging."
        )

    # Remediation SQL for severe operations
    if severity in ("Breaking", "Critical"):
        remediation = generate_remediation_sql(table, operations, column=column, new_column=new_column)
        if remediation:
            lines.append("")
            lines.append("**Safe migration pattern:**")
            lines.append("```sql")
            lines.append(remediation)
            lines.append("```")

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
        column="shipping_address",
    ))
    print("\n--- Test: DROP with downstream ---")
    print(template_explanation(
        table="orders",
        operations=["DROP"],
        severity="Breaking",
        downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DATASET"}],
        column="shipping_address",
    ))
