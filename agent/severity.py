"""
severity.py

REFACTORED: classifies severity PER OPERATION (per column), not per migration.

This replaces the old classify_severity(operations, downstream_count, is_pii)
signature, which collapsed an entire multi-column migration into one severity
label. Now every operation in a migration gets its own independent verdict.

Known, intentional design choices carried over from the locked project brief:
- TYPE_CHANGE is Breaking by default, even when it "looks" compatible
  (e.g. INT -> BIGINT). This is deliberately conservative and documented
  as such in the README, not silently relaxed based on downstream_count.
  We DO expose an `urgency` field (high/low) alongside the severity so the
  report can show nuance without reversing the locked decision.
- DROP+ADD rename ambiguity is NOT resolved here. This function classifies
  operations independently; the rename *note* is a separate, aggregate-level
  heuristic (see rename_heuristic.py) applied across the whole operation
  list, not a change to any individual operation's severity.
- Unknown/unparseable operations default to Breaking (risky), never Safe/Low.
  Silence or parser failure should never look like a green light.
"""

from typing import Optional, List, Dict, Any

KNOWN_OPS = {"ADD", "DROP", "TYPE_CHANGE", "RENAME", "SET_NOT_NULL", "DROP_TABLE", "TRUNCATE"}


def classify_operation(
    op: Dict[str, Any],
    downstream_count: int,
    is_pii: bool = False,
) -> Dict[str, Any]:
    """
    Classify a SINGLE operation.

    Args:
        op: dict describing one parsed operation, e.g.
            {"action": "DROP", "column": "shipping_address"}
            {"action": "ADD", "column": "status", "type": "VARCHAR",
             "nullable": False, "default": None}
        downstream_count: number of downstream assets found for this
            operation's column (see the honesty note in report_builder.py
            about whether this is truly column-level or a table-level
            approximation).
        is_pii: whether this specific column is tagged as PII/sensitive
            in DataHub (same caveat as above).

    Returns:
        dict with: column, action, severity, reason, governance_flags,
        and (for TYPE_CHANGE only) urgency.
    """
    action = (op.get("action") or "UNKNOWN").upper()
    column = op.get("column", "?")
    governance_flags: List[str] = []

    # --- Table-level destructive operations: always Critical ---
    if action in ("DROP_TABLE", "TRUNCATE"):
        return {
            "column": column,
            "action": action,
            "severity": "Critical",
            "reason": "Table-level destructive operation — all data and every "
                      "downstream dependent is affected, regardless of column.",
            "governance_flags": governance_flags,
        }

    # --- Unrecognized operations: never treat silence as safety ---
    if action not in KNOWN_OPS:
        return {
            "column": column,
            "action": action,
            "severity": "Breaking",
            "reason": "Unrecognized or unparseable operation — treated as risky "
                      "by default. Manual review required before merging.",
            "governance_flags": governance_flags,
        }

    # --- ADD ---
    if action == "ADD":
        nullable = op.get("nullable", True)
        default = op.get("default")

        if is_pii:
            governance_flags.append("NEW_PII_COLUMN_ADDED")

        if nullable is False and not default:
            return {
                "column": column,
                "action": action,
                "severity": "Breaking",
                "reason": "Adding a NOT NULL column with no default value will "
                          "fail on any existing rows.",
                "governance_flags": governance_flags,
            }

        return {
            "column": column,
            "action": action,
            "severity": "Safe",
            "reason": "Additive, nullable-or-defaulted column — existing rows "
                      "and downstream consumers are unaffected.",
            "governance_flags": governance_flags,
        }

    # --- DROP ---
    if action == "DROP":
        if is_pii:
            return {
                "column": column,
                "action": action,
                "severity": "Critical",
                "reason": f"Drop of a PII-tagged column with {downstream_count} "
                          f"downstream consumer(s).",
                "governance_flags": governance_flags,
            }
        if downstream_count > 0:
            return {
                "column": column,
                "action": action,
                "severity": "Breaking",
                "reason": f"Column dropped with {downstream_count} downstream "
                          f"dependent(s).",
                "governance_flags": governance_flags,
            }
        return {
            "column": column,
            "action": action,
            "severity": "Low",
            "reason": "Column dropped with no downstream dependents found in "
                      "DataHub's lineage graph.",
            "governance_flags": governance_flags,
        }

    # --- TYPE_CHANGE ---
    if action == "TYPE_CHANGE":
        urgency = "high" if downstream_count > 0 else "low"
        if is_pii:
            return {
                "column": column,
                "action": action,
                "severity": "Critical",
                "reason": f"Type change on a PII-tagged column "
                          f"({downstream_count} downstream dependent(s)).",
                "governance_flags": governance_flags,
                "urgency": urgency,
            }
        return {
            "column": column,
            "action": action,
            "severity": "Breaking",
            "reason": "Type changes are treated as Breaking by design, even when "
                      f"they look compatible (deliberately conservative — see "
                      f"README). Downstream dependents: {downstream_count} "
                      f"(urgency: {urgency}).",
            "governance_flags": governance_flags,
            "urgency": urgency,
        }

    # --- RENAME (explicit ALTER TABLE ... RENAME COLUMN) ---
    if action == "RENAME":
        if downstream_count > 0:
            return {
                "column": column,
                "action": action,
                "severity": "Breaking",
                "reason": f"Column rename — {downstream_count} downstream "
                          f"consumer(s) referencing the old name will break, "
                          f"even though the data itself is preserved.",
                "governance_flags": governance_flags,
            }
        return {
            "column": column,
            "action": action,
            "severity": "Low",
            "reason": "Column rename with no downstream dependents found.",
            "governance_flags": governance_flags,
        }

    # --- SET_NOT_NULL (constraint added to an EXISTING column) ---
    if action == "SET_NOT_NULL":
        return {
            "column": column,
            "action": action,
            "severity": "Breaking",
            "reason": "Adding a NOT NULL constraint to an existing column will "
                      "fail on any existing NULL rows. This is a write-path risk, "
                      "independent of downstream read lineage.",
            "governance_flags": governance_flags,
        }

    # Safety net — should be unreachable given KNOWN_OPS check above.
    return {
        "column": column,
        "action": action,
        "severity": "Breaking",
        "reason": "Unhandled case — defaulting to conservative classification.",
        "governance_flags": governance_flags,
    }


def classify_migration(
    operations: List[Dict[str, Any]],
    downstream_lookup: Dict[str, int],
    pii_lookup: Dict[str, bool],
) -> List[Dict[str, Any]]:
    """
    Classify every operation in a migration independently.

    downstream_lookup / pii_lookup: column_name -> value. Callers (report_builder.py)
    are responsible for populating these per-column, with the caveat documented there
    about table-level vs. column-level lineage granularity.
    """
    results = []
    for op in operations:
        column = op.get("column", "?")
        downstream_count = downstream_lookup.get(column, 0)
        is_pii = pii_lookup.get(column, False)
        results.append(classify_operation(op, downstream_count, is_pii))
    return results


if __name__ == "__main__":
    # Quick smoke test covering every branch, including the new edge cases.
    test_ops = [
        {"action": "DROP", "column": "shipping_address"},
        {"action": "DROP", "column": "temp_debug_id"},
        {"action": "ADD", "column": "status", "type": "VARCHAR", "nullable": True},
        {"action": "ADD", "column": "email", "type": "VARCHAR", "nullable": False, "default": None},
        {"action": "TYPE_CHANGE", "column": "total_amount"},
        {"action": "RENAME", "column": "old_name"},
        {"action": "SET_NOT_NULL", "column": "customer_id"},
        {"action": "DROP_TABLE", "column": None},
        {"action": "WEIRD_UNSUPPORTED_OP", "column": "mystery_col"},
    ]
    downstream = {"shipping_address": 3, "temp_debug_id": 0, "total_amount": 1, "old_name": 2, "customer_id": 0}
    pii = {"shipping_address": True}

    for result in classify_migration(test_ops, downstream, pii):
        print(result)
