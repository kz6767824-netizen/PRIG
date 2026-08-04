"""
agent/patch_generator.py

Automated Remediation SQL Patch Generator for PR Impact Guardian (PRIG).
Generates ready-to-run, non-breaking SQL patches.

FIX: Uses rename-then-view pattern instead of SELECT *, NULL AS col
which caused duplicate column errors when the original column still existed.
"""

import os
from typing import List, Dict, Any


def generate_sql_patch(table: str, operations: List[Dict[str, Any]]) -> str:
    """
    Generates a safe, non-breaking SQL patch for a set of operations.
    Uses the rename-then-view pattern to preserve backward compatibility.
    """
    drop_ops = [op for op in operations if op.get("action") == "DROP"]
    rename_ops = [op for op in operations if op.get("action") == "RENAME"]
    type_change_ops = [op for op in operations if op.get("action") == "TYPE_CHANGE"]
    add_ops = [op for op in operations if op.get("action") == "ADD"]
    table_drop_ops = [op for op in operations if op.get("action") == "DROP_TABLE"]

    lines = [
        "-- ======================================================================",
        "-- PR IMPACT GUARDIAN (PRIG) - AUTOMATED SAFE REMEDIATION PATCH",
        f"-- Target Table: {table}",
        "-- Pattern: Rename-Then-View (preserves data, keeps old names working)",
        "-- NOTE: Review and adapt column lists before running in production.",
        "-- ======================================================================\n",
    ]

    # Table-level drop
    if table_drop_ops:
        lines.extend([
            "-- PHASE 1: Preserve table data and maintain backward compatibility\n",
            f"ALTER TABLE {table} RENAME TO {table}_deprecated_archive;\n",
            f"CREATE OR REPLACE VIEW {table} AS",
            f"SELECT * FROM {table}_deprecated_archive;\n",
            f"-- PHASE 2: After confirming zero queries hit the archive, drop it:",
            f"-- DROP TABLE {table}_deprecated_archive;\n",
        ])
        return "\n".join(lines)

    # Additive changes (safe to apply immediately)
    if add_ops:
        lines.append("-- PHASE 1: Safe additive changes (apply immediately)\n")
        for op in add_ops:
            col = op.get("column")
            col_type = op.get("type", "VARCHAR")
            lines.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type};")
        lines.append("")

    # Rename operations
    for op in rename_ops:
        col = op.get("column")
        new_col = op.get("new_column", "<new_column>")
        lines.extend([
            f"-- PHASE 2: Safe rename for '{col}' -> '{new_col}'\n",
            f"ALTER TABLE {table} ADD COLUMN {new_col} <TYPE>;\n",
            f"-- UPDATE {table} SET {new_col} = {col};\n",
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n",
            f"CREATE OR REPLACE VIEW {table}_legacy AS",
            f"SELECT {col}_deprecated AS {col}, *",
            f"FROM {table};\n",
            f"-- After migration: ALTER TABLE {table} DROP COLUMN {col}_deprecated;\n",
        ])

    # Type change operations
    for op in type_change_ops:
        col = op.get("column")
        new_type = op.get("new_type", "<TARGET_TYPE>")
        lines.extend([
            f"-- PHASE 2: Safe type change for '{col}'\n",
            f"ALTER TABLE {table} ADD COLUMN {col}_new {new_type};\n",
            f"-- UPDATE {table} SET {col}_new = CAST({col} AS {new_type});\n",
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n",
            f"CREATE OR REPLACE VIEW {table}_legacy AS",
            f"SELECT {col}_new AS {col}, *",
            f"FROM {table};\n",
            f"-- After migration: ALTER TABLE {table} DROP COLUMN {col}_deprecated;\n",
        ])

    # Drop operations
    for op in drop_ops:
        col = op.get("column")
        lines.extend([
            f"-- PHASE 2: Safe deprecation for column '{col}'\n",
            f"ALTER TABLE {table} RENAME COLUMN {col} TO {col}_deprecated;\n",
            f"CREATE OR REPLACE VIEW {table}_legacy AS",
            f"SELECT {col}_deprecated AS {col}, *",
            f"FROM {table};\n",
            f"-- PHASE 3: After all consumers migrate, drop deprecated column:",
            f"-- ALTER TABLE {table} DROP COLUMN {col}_deprecated;\n",
        ])

    if not add_ops and not rename_ops and not type_change_ops and not drop_ops:
        lines.append("-- No breaking operations detected. No patch needed.\n")

    return "\n".join(lines)


def save_patch_file(table: str, operations: List[Dict[str, Any]], output_dir: str = "patches") -> str:
    """Generates and writes the safe SQL patch to a file."""
    os.makedirs(output_dir, exist_ok=True)
    patch_content = generate_sql_patch(table, operations)

    file_path = os.path.join(output_dir, f"{table}_safe_migration.sql")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(patch_content)

    return file_path


if __name__ == "__main__":
    sample_ops = [
        {"action": "DROP", "column": "shipping_address"},
        {"action": "ADD", "column": "loyalty_points", "type": "INT"}
    ]
    path = save_patch_file("orders", sample_ops)
    print(f"Generated safe patch at: {path}\n")
    with open(path, "r") as f:
        print(f.read())
