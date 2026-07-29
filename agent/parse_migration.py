"""
parse_migration.py

Extends the ALREADY-TESTED approach from test_sql_parser.py (sqlparse for
statement structure + table-name extraction) rather than starting from an
unverified regex file. What's new here is per-clause extraction of column
name, type, nullable, and default -- the original tested parser only
detected which operation TYPES were present in the whole statement, not
per-column detail.

Approach:
  1. Use sqlparse to parse the statement and locate the table name, exactly
     like the original tested parser did (this part is unchanged/proven).
  2. Take the raw text AFTER "ALTER TABLE <table>" and split it into
     individual clauses on top-level commas (commas inside parentheses,
     e.g. VARCHAR(10,2), are NOT split points -- this is new logic, tested
     below against the DECIMAL(10,2) case specifically).
  3. Classify each clause independently with a small, targeted pattern for
     that clause only (not one giant regex over the whole raw SQL text,
     which is what the original parser did and what made it unable to
     return per-column detail).
  4. DROP TABLE is handled as a separate top-level case, since it's not a
     column-level clause at all.

Known, explicitly deferred (NOT implemented in this version):
  - SET NOT NULL as its own operation type. It shares the
    "ALTER COLUMN <name>" prefix with TYPE_CHANGE and deliberately needs
    its own dedicated test pass rather than being bundled into this one,
    per the agreed sequencing.
  - RENAME COLUMN ... TO ... is included since it was already covered by
    the earlier (unverified) draft and is structurally unambiguous, but
    it has NOT been tested here yet -- flagged below, not claimed as proven.
  - Multi-table migrations, CHECK constraints, index/FK changes, quoted
    or schema-qualified identifiers (e.g. "public"."orders") are not
    handled and are not claimed to be.
"""

import re
from typing import List, Dict, Any, Optional

import sqlparse
from sqlparse.tokens import Keyword, Punctuation


def _extract_table_name(stmt) -> Optional[str]:
    """Unchanged approach from the original tested parser."""
    tokens = [t for t in stmt.tokens if not t.is_whitespace]
    for i, token in enumerate(tokens):
        if token.ttype is Keyword and token.value.upper() == "TABLE":
            if i + 1 < len(tokens):
                return str(tokens[i + 1]).strip().strip('"\'`[]')
    return None


def _split_top_level_clauses(text: str) -> List[str]:
    """
    Splits on commas NOT inside parentheses, so 'DECIMAL(10,2)' stays intact
    as one clause fragment rather than being split at the inner comma.
    """
    parts = []
    depth = 0
    current = []
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return [p.strip().rstrip(";").strip() for p in parts if p.strip().rstrip(";").strip()]


def _parse_add_clause(clause: str) -> Optional[Dict[str, Any]]:
    m = re.match(
        r'^ADD\s+(?:COLUMN\s+)?([A-Za-z_]\w*)\s+([A-Za-z_]\w*(?:\s*\([^)]*\))?)(.*)$',
        clause, re.IGNORECASE,
    )
    if not m:
        return None
    column, col_type, rest = m.group(1), m.group(2).strip(), m.group(3)

    nullable = True
    if re.search(r'\bNOT\s+NULL\b', rest, re.IGNORECASE):
        nullable = False

    default = None
    dm = re.search(r"DEFAULT\s+('[^']*'|\"[^\"]*\"|\S+)", rest, re.IGNORECASE)
    if dm:
        default = dm.group(1).strip("'\"")

    return {
        "action": "ADD",
        "column": column,
        "type": col_type,
        "nullable": nullable,
        "default": default,
    }


def _parse_drop_clause(clause: str) -> Optional[Dict[str, Any]]:
    m = re.match(r'^DROP\s+(?:COLUMN\s+)?([A-Za-z_]\w*)\s*$', clause, re.IGNORECASE)
    if not m:
        return None
    return {"action": "DROP", "column": m.group(1)}


def _parse_type_change_clause(clause: str) -> Optional[Dict[str, Any]]:
    m = re.match(
        r'^ALTER\s+(?:COLUMN\s+)?([A-Za-z_]\w*)\s+(?:TYPE|SET\s+DATA\s+TYPE)\s+'
        r'([A-Za-z_]\w*(?:\s*\([^)]*\))?)\s*$',
        clause, re.IGNORECASE,
    )
    if not m:
        return None
    return {"action": "TYPE_CHANGE", "column": m.group(1), "new_type": m.group(2).strip()}


def _parse_rename_clause(clause: str) -> Optional[Dict[str, Any]]:
    # NOT independently tested below yet -- flagged, not proven.
    m = re.match(
        r'^RENAME\s+(?:COLUMN\s+)?([A-Za-z_]\w*)\s+TO\s+([A-Za-z_]\w*)\s*$',
        clause, re.IGNORECASE,
    )
    if not m:
        return None
    return {"action": "RENAME", "column": m.group(1), "new_column": m.group(2)}


def parse_migration(sql_text: str) -> Dict[str, Any]:
    sql_text = sql_text.strip()
    if not sql_text:
        return {"table": None, "operations": []}

    # --- DROP TABLE: handled separately, not a column-level clause ---
    m = re.match(r'^DROP\s+TABLE\s+([A-Za-z_]\w*)', sql_text, re.IGNORECASE)
    if m:
        return {
            "table": m.group(1),
            "operations": [{"action": "DROP_TABLE", "column": None}],
        }

    parsed = sqlparse.parse(sql_text)
    if not parsed:
        return {"table": None, "operations": []}

    table = _extract_table_name(parsed[0])
    if not table:
        return {"table": None, "operations": []}

    # Strip the "ALTER TABLE <table>" prefix to get the clause text.
    prefix_match = re.search(
        r'ALTER\s+TABLE\s+' + re.escape(table) + r'\s*', sql_text, re.IGNORECASE
    )
    remainder = sql_text[prefix_match.end():] if prefix_match else sql_text

    operations = []
    for clause in _split_top_level_clauses(remainder):
        parsed_op = (
            _parse_drop_clause(clause)
            or _parse_add_clause(clause)
            or _parse_type_change_clause(clause)
            or _parse_rename_clause(clause)
        )
        if parsed_op:
            operations.append(parsed_op)
        else:
            # Never silently drop a clause we couldn't classify -- surface it.
            operations.append({"action": "UNKNOWN", "column": None, "raw_clause": clause})

    return {"table": table, "operations": operations}


if __name__ == "__main__":
    # --- The 3 ORIGINAL test cases, re-run against the upgraded parser ---
    test_1 = """
    ALTER TABLE orders
      DROP COLUMN shipping_address,
      ADD COLUMN status VARCHAR;
    """

    test_2 = """
    ALTER TABLE orders
      ALTER COLUMN total_amount TYPE DECIMAL(10,2);
    """

    test_3 = """
    ALTER TABLE orders
      ADD COLUMN loyalty_points INT;
    """

    # --- NEW cases with column-level detail ---
    test_4 = """
    ALTER TABLE orders
      ADD COLUMN email VARCHAR NOT NULL DEFAULT 'unknown';
    """

    test_5 = "DROP TABLE old_staging_table;"

    # --- NEW: RENAME, previously untested ---
    test_6 = """
    ALTER TABLE orders
      RENAME COLUMN shipping_address TO delivery_address;
    """

    for i, sql in enumerate([test_1, test_2, test_3, test_4, test_5, test_6], 1):
        print(f"--- Test {i} ---")
        print(parse_migration(sql))
        print()
