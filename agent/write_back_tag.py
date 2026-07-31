"""
write_back_tag.py

FIX: ensure_tags_exist() is now called with the SINGLE specific tag name
about to be applied -- not all four every time. write_back_tag() only
ever applies one tag per call, so creating the others was unnecessary
API calls with no benefit.
"""

from typing import Optional, Dict, Any

SEVERITY_TO_TAG = {
    "Critical": "urn:li:tag:pending-review-critical",
    "Breaking": "urn:li:tag:pending-review-breaking",
    # Safe and Low: no tag written -- intentional, per the agreed threshold.
}


def write_back_tag(
    table_urn: str,
    overall_severity: str,
    dry_run: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Args:
        table_urn: the dataset URN to tag (whole-entity).
        overall_severity: result of compute_overall_severity().
        dry_run: if True (default), only prints what would happen and
            makes NO live API call.

    Returns:
        The add_tags() result dict if a real write happened, or a dict
        describing the dry-run action if not, or None if severity is
        Safe/Low (no write-back needed at all).
    """
    tag_urn = SEVERITY_TO_TAG.get(overall_severity)

    if tag_urn is None:
        print(f"[write_back_tag] Overall severity is '{overall_severity}' "
              f"-- no tag written (below threshold).")
        return None

    if dry_run:
        print(f"[write_back_tag] DRY RUN -- would apply tag '{tag_urn}' "
              f"to '{table_urn}' (overall severity: {overall_severity}). "
              f"No live write performed. Set dry_run=False to actually write.")
        return {"dry_run": True, "would_apply_tag": tag_urn, "entity_urn": table_urn}

    # Real write -- ensure ONLY this specific tag exists first, then apply it.
    from ensure_tags_exist import ensure_tags_exist
    from datahub_agent_context.mcp_tools import add_tags

    tag_name = tag_urn.split(":")[-1]  # "urn:li:tag:pending-review-breaking" -> "pending-review-breaking"
    ensure_tags_exist(tag_names=[tag_name])

    result = add_tags(
        tag_urns=[tag_urn],
        entity_urns=[table_urn],
    )
    print(f"[write_back_tag] LIVE WRITE -- applied '{tag_urn}' to "
          f"'{table_urn}'. Result: {result}")
    return result


if __name__ == "__main__":
    # Offline-safe tests -- all dry_run=True (default), no DataHub needed.
    print("--- Safe (should skip entirely) ---")
    print(write_back_tag("urn:li:dataset:(...)", "Safe"))
    print()
    print("--- Low (should skip entirely) ---")
    print(write_back_tag("urn:li:dataset:(...)", "Low"))
    print()
    print("--- Breaking (dry run) ---")
    print(write_back_tag("urn:li:dataset:(...)", "Breaking"))
    print()
    print("--- Critical (dry run) ---")
    print(write_back_tag("urn:li:dataset:(...)", "Critical"))
