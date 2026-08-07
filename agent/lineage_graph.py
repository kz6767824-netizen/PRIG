"""
lineage_graph.py

Builds a Mermaid flowchart string from a table name and its downstream
assets (as returned by report_builder.get_downstream_assets()). Shared
by both the Streamlit app and the GitHub Action, so the graph rendered
in a PR comment matches the one rendered in the live demo.

GitHub renders ```mermaid fenced blocks natively in PR comments and
markdown files -- no image generation needed. Streamlit does NOT render
Mermaid natively, so app.py loads mermaid.js from CDN via
streamlit.components.v1.html to render the same string.

Purely visual -- no click links.
"""

from typing import List, Dict, Any


def build_mermaid_graph(table: str, downstream_assets: List[Dict[str, Any]]) -> str:
    safe_id = "".join(c if c.isalnum() else "_" for c in table)
    lines = ["graph LR", f'  {safe_id}["{table}"]']

    if not downstream_assets:
        lines.append(f'  {safe_id} -.->|no downstream assets found| {safe_id}_none["(none)"]')
        return "\n".join(lines)

    for i, asset in enumerate(downstream_assets):
        node_id = f"{safe_id}_d{i}"
        name = asset.get("name", "unknown")
        atype = asset.get("type", "unknown")
        lines.append(f'  {safe_id} --> {node_id}["{name}<br/><i>{atype}</i>"]')

    return "\n".join(lines)
