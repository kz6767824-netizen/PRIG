"""
severity_rollup.py

compute_overall_severity(): rolls up per-column severities (from
classify_migration()) into ONE overall severity for the whole migration.

Precedence, highest wins: Critical > Breaking > Low > Safe
"""
from typing import List, Dict, Any

SEVERITY_RANK = {"Safe": 0, "Low": 1, "Breaking": 2, "Critical": 3}
RANK_TO_SEVERITY = {v: k for k, v in SEVERITY_RANK.items()}


def compute_overall_severity(classified_operations: List[Dict[str, Any]]) -> str:
    """
    Args:
        classified_operations: output of severity.classify_migration() --
            a list of dicts each containing a 'severity' key.
    Returns:
        The single highest-ranked severity string found across all
        operations. Defaults to "Safe" only if the list is empty (no
        operations at all -- an edge case, not expected in real use).
    """
    if not classified_operations:
        return "Safe"
    highest_rank = max(
        SEVERITY_RANK.get(op.get("severity", "Safe"), 0)
        for op in classified_operations
    )
    return RANK_TO_SEVERITY[highest_rank]


if __name__ == "__main__":
    test_cases = [
        ("All Safe", [{"severity": "Safe"}, {"severity": "Safe"}]),
        ("Mixed Safe+Low", [{"severity": "Safe"}, {"severity": "Low"}]),
        ("Mixed Safe+Breaking", [{"severity": "Safe"}, {"severity": "Breaking"}]),
        ("Mixed Breaking+Critical", [{"severity": "Breaking"}, {"severity": "Critical"}]),
        ("Single Critical", [{"severity": "Critical"}]),
        ("Empty list", []),
    ]
    for label, ops in test_cases:
        result = compute_overall_severity(ops)
        print(f"{label}: {result}")
