"""
write_back_context_document.py

Saves the full PR Impact Report as a DataHub Context Document, linked to
the affected table -- the permanent, per-instance detail layer alongside
the ephemeral pending-review-* tag.

Verified against the REAL save_document() signature (inspected directly
from your installed datahub_agent_context package, not assumed):

    save_document(
        document_type: Literal['Insight','Decision','FAQ','Analysis',
                                'Summary','Recommendation','Note','Context'],
        title: str,
        content: str,
        urn: Optional[str] = None,
        topics: Optional[List[str]] = None,
        related_documents: Optional[List[str]] = None,
        related_assets: Optional[List[str]] = None,
    ) -> dict

NOTE on document_type: DataHub's UI-level docs describe categories like
"Runbook, FAQ, Policy, Decision Log" -- but those are NOT the literal
values save_document() accepts. We use "Decision" (the closest real,
confirmed value) since a PR Impact Report documents a decision point
about a proposed schema change. This mapping is my best inference, not
independently confirmed against the UI -- worth checking visually in
DataHub after the first real write, same as we did for tags.

Confirmed via docs.datahub.com: Context Documents work on SELF-HOSTED
DataHub (not Cloud-only), and are created in PUBLISHED state by default.
"""

from typing import Optional, Dict, Any


def write_back_context_document(
    table: str,
    table_urn: str,
    report_content: str,
    overall_severity: str,
    dry_run: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Args:
        table: table name, used in the document title.
        table_urn: dataset URN to link this document to (related_assets).
        report_content: the full markdown report text (from
            build_full_report()) -- saved as-is as the document content.
        overall_severity: used in the title and topics for discoverability.
        dry_run: if True (default), only prints what would happen, makes
            NO live API call. Must be explicitly set to False to write.

    Returns:
        The save_document() result dict if a real write happened, or a
        dict describing the dry-run action if not.
    """
    title = f"PR Impact Report: {table} ({overall_severity})"
    topics = ["pr-impact-guardian", "schema-change", overall_severity.lower()]

    if dry_run:
        print(f"[write_back_context_document] DRY RUN -- would save a "
              f"Context Document:")
        print(f"    title: {title}")
        print(f"    document_type: Decision")
        print(f"    related_assets: [{table_urn}]")
        print(f"    topics: {topics}")
        print(f"    content length: {len(report_content)} chars")
        print(f"  No live write performed. Set dry_run=False to actually write.")
        return {
            "dry_run": True,
            "would_save_title": title,
            "related_assets": [table_urn],
        }

    # Real write -- only reached when dry_run=False.
    from datahub_agent_context.mcp_tools import save_document
    result = save_document(
        document_type="Decision",
        title=title,
        content=report_content,
        topics=topics,
        related_assets=[table_urn],
    )
    print(f"[write_back_context_document] LIVE WRITE -- saved document "
          f"'{title}'. Result: {result}")
    return result


if __name__ == "__main__":
    # Offline-safe test -- dry_run=True (default), no DataHub needed.
    sample_report = (
        "# PR Impact Report: `orders`\n\n"
        "## Column: `shipping_address`\n"
        "Severity: Breaking\n"
        "Downstream impact (1 asset): daily_revenue_dashboard\n"
    )
    result = write_back_context_document(
        table="orders",
        table_urn="urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
        report_content=sample_report,
        overall_severity="Breaking",
    )
    print()
    print("Returned:", result)
