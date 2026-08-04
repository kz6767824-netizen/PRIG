"""
llm_explanation.py

Generates the explanation/suggestion text using an LLM (Groq), grounded in
the SAME raw facts the deterministic template uses. If the LLM call fails
for ANY reason, automatically falls back to template_explanation().

FIX: fallback call now uses keyword arguments to avoid positional-arg mismatch
with template_explanation()'s signature.
"""

import os
from typing import List, Dict, Any, Optional

from explainer import template_explanation


def _build_prompt(
    table: str,
    column: str,
    operation: str,
    severity: str,
    downstream_assets: List[Dict[str, Any]],
    is_pii: bool,
    governance_flags: Optional[List[str]],
    new_column: Optional[str] = None,
) -> str:
    """Builds a prompt from the RAW FACTS -- same inputs as the template."""
    downstream_desc = (
        ", ".join(f"{a['name']} ({a.get('type', 'unknown')})" for a in downstream_assets)
        if downstream_assets else "none found"
    )
    dashboard_count = sum(1 for a in downstream_assets if a.get("type", "").upper() == "DASHBOARD")

    column_desc = f"the '{column}' column" if column else "the whole table (table-level operation)"
    rename_desc = f"\nRenamed to: '{new_column}'" if operation == "RENAME" and new_column else ""

    sql_request = ""
    if severity in ("Breaking", "Critical"):
        sql_request = (
            "\n\nAlso provide a short, safe SQL refactoring snippet (e.g. rename-then-view, "
            "or add-new-column-then-migrate) inside a ```sql block. Keep it under 10 lines."
        )

    return f"""You are writing one section of a schema-change impact report for a data engineering team. Be concrete and concise (3-5 sentences).

CRITICAL: The downstream assets have ALREADY been identified and listed below. Do NOT tell the user to "check dependencies" or "investigate downstream impact" — that work is already done by the tool. Instead, give concrete next steps referencing the specific assets by name.

Table: {table}
Affected: {column_desc}
Operation: {operation}{rename_desc}
Severity (already determined, do not change or second-guess it): {severity}
Downstream assets already found: {downstream_desc}
Number of downstream assets that are dashboards (user-facing): {dashboard_count}
Column is tagged PII: {is_pii}
Governance flags: {governance_flags or 'none'}{sql_request}

Write a short, clear explanation of the risk and a concrete suggested action. Refer to specific downstream assets by name. Do not add a disclaimer — one is appended separately in the report."""


def llm_explanation(
    table: str,
    column: Optional[str],
    operation: str,
    severity: str,
    downstream_assets: List[Dict[str, Any]],
    is_pii: bool = False,
    governance_flags: Optional[List[str]] = None,
    new_column: Optional[str] = None,
) -> str:
    """
    Returns an LLM-generated explanation if possible, otherwise falls back
    to the deterministic template.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[llm_explanation] No GROQ_API_KEY found -- falling back to template.")
        return template_explanation(
            table=table,
            operations=[operation],
            severity=severity,
            downstream_assets=downstream_assets,
            is_pii=is_pii,
            governance_flags=governance_flags,
            new_column=new_column,
            column=column,
        )

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        prompt = _build_prompt(
            table, column, operation, severity, downstream_assets, is_pii, governance_flags, new_column
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=450,
        )
        text = response.choices[0].message.content.strip()
        if not text:
            raise ValueError("LLM returned empty content")

        header = (
            f"- **Table:** `{table}`\n"
            f"- **Column:** `{column or 'N/A (table-level)'}`\n"
            f"- **Severity:** `{severity}`\n"
        )
        return header + "\n" + text

    except Exception as e:
        print(f"[llm_explanation] LLM call failed ({type(e).__name__}: {e}) -- falling back to template.")
        return template_explanation(
            table=table,
            operations=[operation],
            severity=severity,
            downstream_assets=downstream_assets,
            is_pii=is_pii,
            governance_flags=governance_flags,
            new_column=new_column,
            column=column,
        )


if __name__ == "__main__":
    os.environ.pop("GROQ_API_KEY", None)
    print("--- Test: no API key (fallback expected) ---")
    result = llm_explanation(
        table="orders",
        column="shipping_address",
        operation="DROP",
        severity="Breaking",
        downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DATASET"}],
        is_pii=False,
    )
    print(result)
