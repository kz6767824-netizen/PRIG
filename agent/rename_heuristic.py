"""
rename_heuristic.py

This is deliberately NOT part of severity.py. Per-operation classification
treats a DROP and an ADD as two fully independent operations (this is the
locked, honest design: the agent cannot know intent from schema alone).

This module adds a separate, aggregate-level NOTE across the whole
operation list: "hey, this DROP and this ADD look like they might be a
rename." It never changes any operation's severity — it only adds
a flag the report can surface to a human, who is the one actually
qualified to know if it's a rename or two unrelated changes.
"""

from typing import List, Dict, Any, Optional, Tuple


def looks_like_rename(operations: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """
    Returns a list of (dropped_column, added_column) pairs that look like
    they might be a rename, based on simple name-similarity heuristics.
    Does NOT claim certainty — this is a heuristic prompt for human review.
    """
    drops = [op["column"] for op in operations if op.get("action") == "DROP" and op.get("column")]
    adds = [op["column"] for op in operations if op.get("action") == "ADD" and op.get("column")]

    candidates = []
    for d in drops:
        for a in adds:
            d_l, a_l = d.lower(), a.lower()
            same_prefix = d_l.split("_")[0] == a_l.split("_")[0]
            versioned = (
                d_l.replace("_old", "") == a_l.replace("_new", "")
                or d_l.replace("_v1", "") == a_l.replace("_v2", "")
            )
            substring_match = d_l in a_l or a_l in d_l
            if same_prefix or versioned or substring_match:
                candidates.append((d, a))
    return candidates


def rename_note(operations: List[Dict[str, Any]]) -> Optional[str]:
    """Returns a human-readable note if a possible rename is detected, else None."""
    candidates = looks_like_rename(operations)
    if not candidates:
        return None

    pairs_str = ", ".join(f"'{d}' -> '{a}'" for d, a in candidates)
    return (
        f"Note: This migration includes both a DROP and an ADD with similar "
        f"names ({pairs_str}). This may be a rename rather than two unrelated "
        f"changes. The agent cannot determine intent — if this IS a rename, "
        f"check whether downstream assets reference the old column name "
        f"directly (e.g. in hardcoded SQL or model definitions), since those "
        f"will break even though the underlying data is preserved."
    )


if __name__ == "__main__":
    ops_rename = [
        {"action": "DROP", "column": "shipping_address"},
        {"action": "ADD", "column": "shipping_address_v2"},
    ]
    ops_unrelated = [
        {"action": "DROP", "column": "temp_debug_id"},
        {"action": "ADD", "column": "loyalty_tier"},
    ]
    print(rename_note(ops_rename))
    print(rename_note(ops_unrelated))
