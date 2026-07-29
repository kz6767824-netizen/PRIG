"""
write_back_tag.py

Maps an overall migration severity to the correct DataHub tag and writes
it back -- or, by default, just prints what WOULD be written (dry_run=True)
so repeated pipeline test runs don't spam duplicate tag-write calls against
the live instance.

IMPORTANT: the tag URNs referenced below (pending-review-breaking,
pending-review-critical) must already exist as real tag entities in
DataHub -- created once via the UI, same as 'pending-review' and 'PII'
were. If they don't exist yet, add_tags() will fail with the same
"Urn does not exist" error seen earlier in this project. This function
does NOT create tags; it only applies existing ones.
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
        table_urn: the dataset URN to tag (whole-entity, matching how
            add_tags was actually tested -- not column-level).
        overall_severity: result of compute_overall_severity().
        dry_run: if True (default), only prints what would happen and
            makes NO live API call. Must be explicitly set to False to
            perform a real write.

    Returns:
        The add_tags() result dict if a real write happened, or a dict
        describing the dry-run action if not, or None if severity is
        Safe/Low (no write-back needed at all, not even a dry-run note).
    """
    tag_urn = SEVERITY_TO_TAG.get(overall_severity)

    if tag_urn is None:
        # Safe or Low -- no write-back at all, by design.
        print(f"[write_back_tag] Overall severity is '{overall_severity}' "
              f"-- no tag written (below threshold).")
        return None

    if dry_run:
        print(f"[write_back_tag] DRY RUN -- would apply tag '{tag_urn}' "
              f"to '{table_urn}' (overall severity: {overall_severity}). "
              f"No live write performed. Set dry_run=False to actually write.")
        return {"dry_run": True, "would_apply_tag": tag_urn, "entity_urn": table_urn}

    # Real write -- only reached when dry_run=False.
    from datahub_agent_context.mcp_tools import add_tags
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
