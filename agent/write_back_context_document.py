"""
write_back_context_document.py

Saves the full PR Impact Report(koza) as a DataHub Context Document, linked to
the affected table -- the permanent detail layer alongside the ephemeral tag.

FIX: Removed attach_report_to_dataset_description() which would have
OVERWRITTEN the dataset's real description with a migration report.

SOURCE TAGGING ADDITION: both functions now accept a `source` argument
identifying WHICH interface produced this write (Streamlit, GitHub Actions,
Slack, etc). Without this, a document saved in DataHub gives no indication
of where it came from -- a teammate finding it months later couldn't tell
whether it was a live PR check or a one-off manual test. The source is
recorded in two places: a human-readable line at the top of the document
content, and a machine-filterable `source-<name>` topic, so documents can
later be filtered/searched by origin in DataHub's own UI.
"""

from typing import Optional, Dict, Any, List

# Human-readable labels shown in the document body. Extend this dict (not
# the function signatures) when a new interface starts writing documents --
# an unrecognized source string still works, it just falls back to a plain
# "Source: <name>" line instead of the icon+description version.
SOURCE_LABELS = {
    "streamlit": "🖥️ Streamlit app (manual check)",
    "github-actions": "⚙️ GitHub Actions (automated PR check)",
    "slack": "💬 Slack (interactive session)",
    "cli": "⌨️ Command line / local script",
}


def _source_line(source: str) -> str:
    label = SOURCE_LABELS.get(source, f"Source: {source}" if source else "Source: unknown")
    return f"> **Source:** {label}\n"


def write_back_context_document(
    table: str,
    table_urn: str,
    report_content: str,
    overall_severity: str,
    dry_run: bool = True,
    source: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """
    Args:
        table: table name, used in the document title.
        table_urn: dataset URN to link this document to (related_assets).
        report_content: the full markdown report text.
        overall_severity: used in the title and topics.
        dry_run: if True (default), only prints what would happen.
        source: which interface produced this write -- "streamlit",
            "github-actions", "slack", "cli", etc. Recorded as a visible
            line in the document body and as a `source-<name>` topic.
            Defaults to "unknown" so existing callers that haven't been
            updated yet don't break -- they just get an honest label
            instead of a wrong guess.

    Returns:
        The save_document() result dict if a real write happened, or a
        dict describing the dry-run action if not.
    """
    title = f"PR Impact Report: {table} ({overall_severity})"
    topics = ["pr-impact-guardian", "schema-change", overall_severity.lower(), f"source-{source}"]
    content = _source_line(source) + "\n" + report_content

    if dry_run:
        print(f"[write_back_context_document] DRY RUN -- would save a "
              f"Context Document:")
        print(f"    title: {title}")
        print(f"    document_type: Decision")
        print(f"    related_assets: [{table_urn}]")
        print(f"    topics: {topics}")
        print(f"    source: {source}")
        print(f"    content length: {len(content)} chars")
        print(f"  No live write performed. Set dry_run=False to actually write.")
        return {
            "dry_run": True,
            "would_save_title": title,
            "related_assets": [table_urn],
            "source": source,
        }

    # Real write
    from datahub_agent_context.mcp_tools import save_document
    result = save_document(
        document_type="Decision",
        title=title,
        content=content,
        topics=topics,
        related_assets=[table_urn],
    )
    print(f"[write_back_context_document] LIVE WRITE -- saved document "
          f"'{title}' (source: {source}). Result: {result}")
    return result


def write_back_combined_context_document(
    tables: List[Dict[str, Any]],
    dry_run: bool = True,
    source: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """
    Saves ONE Context Document covering every table in a multi-table
    migration, instead of a separate document per table. Linked to all
    affected tables via related_assets, with one section per table in the
    content body -- so a reviewer browsing DataHub sees the whole PR's
    impact in one place instead of hunting down N disconnected documents.

    Does not replace write_back_context_document() above -- that function
    is left untouched since interactive_agent.py (single-table session)
    still calls it directly.

    Args:
        tables: list of dicts, one per table, each with keys:
            "table" (str), "table_urn" (str), "report_content" (str),
            "overall_severity" (str).
        dry_run: if True (default), only prints what would happen.
        source: which interface produced this write. See
            write_back_context_document() above for details -- same
            behavior here, just applied once to the combined document
            instead of once per table.

    Returns:
        The save_document() result dict if a real write happened, or a
        dict describing the dry-run action if not.
    """
    if not tables:
        raise ValueError("write_back_combined_context_document() called with no tables")

    table_names = [t["table"] for t in tables]
    table_urns = [t["table_urn"] for t in tables]
    severities = [t["overall_severity"] for t in tables]

    # Highest-severity-first ordering for the title, e.g. "Critical" migrations
    # should read as such even if most tables in the batch are "Safe".
    severity_rank = {"Critical": 0, "Breaking": 1, "Low": 2, "Safe": 3}
    worst_severity = min(severities, key=lambda s: severity_rank.get(s, 99))

    title = f"koza Impact Report: {', '.join(table_names)} ({worst_severity})"
    topics = ["koza-impact-guardian", "schema-change", "multi-table", f"source-{source}"]
    topics += sorted({s.lower() for s in severities})

    content_sections = [
        f"# koza Impact Report -- Combined ({len(tables)} tables)\n",
        _source_line(source),
        f"**Tables in this migration:** {', '.join(table_names)}\n",
        f"**Highest severity:** `{worst_severity}`\n",
        "\n---\n",
    ]
    for t in tables:
        content_sections.append(t["report_content"])
        content_sections.append("\n---\n")
    content = "\n".join(content_sections)

    if dry_run:
        print(f"[write_back_combined_context_document] DRY RUN -- would save a "
              f"Context Document:")
        print(f"    title: {title}")
        print(f"    document_type: Decision")
        print(f"    related_assets: {table_urns}")
        print(f"    topics: {topics}")
        print(f"    source: {source}")
        print(f"    content length: {len(content)} chars")
        print(f"  No live write performed. Set dry_run=False to actually write.")
        return {
            "dry_run": True,
            "would_save_title": title,
            "related_assets": table_urns,
            "source": source,
        }

    # Real write
    from datahub_agent_context.mcp_tools import save_document
    result = save_document(
        document_type="Decision",
        title=title,
        content=content,
        topics=topics,
        related_assets=table_urns,
    )
    print(f"[write_back_combined_context_document] LIVE WRITE -- saved document "
          f"'{title}' (source: {source}). Result: {result}")
    return result


if __name__ == "__main__":
    sample_report = (
        "# koza Impact Report: `orders`\n\n"
        "## Column: `shipping_address`\n"
        "Severity: Breaking\n"
        "Downstream impact (1 asset): daily_revenue_dashboard\n"
    )
    result = write_back_context_document(
        table="orders",
        table_urn="urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
        report_content=sample_report,
        overall_severity="Breaking",
        source="streamlit",
    )
    print()
    print("Returned:", result)

    print("\n--- Combined, source=github-actions ---")
    result2 = write_back_combined_context_document(
        tables=[
            {
                "table": "orders",
                "table_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
                "report_content": sample_report,
                "overall_severity": "Breaking",
            },
            {
                "table": "customers",
                "table_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)",
                "report_content": "# koza Impact Report: `customers`\n\nSeverity: Safe\n",
                "overall_severity": "Safe",
            },
        ],
        source="github-actions",
    )
    print()
    print("Returned:", result2)
