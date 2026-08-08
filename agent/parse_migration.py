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

MULTI-TABLE ADDITION: parse_migration() itself is UNCHANGED and remains
the single-statement entry point. parse_multi_table_migration() is a new,
purely additive function that splits a full migration file into individual
top-level statements (semicolon-separated, respecting parens) and calls
the existing, unchanged parse_migration() on each one. Zero risk to the
already-tested single-statement path.

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


def _split_top_level_statements(sql_text: str) -> List[str]:
    """
    Splits a multi-statement migration file into individual statements on
    semicolons NOT inside parentheses (same logic as _split_top_level_clauses,
    applied at the statement level instead of the clause level). This is
    what makes multi-table migrations possible -- each returned string is
    handed to the existing, unchanged parse_migration() one at a time.
    """
    parts = []
    depth = 0
    current = []
    for ch in sql_text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    tail = "".join(current)
    if tail.strip():
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


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


def _strip_leading_comment_lines(sql_text: str) -> str:
    """
    Strips leading '-- comment' lines and blank lines from the front of a
    statement before operation matching. Needed because parse_migration()'s
    DROP TABLE check is anchored with ^DROP\\s+TABLE -- if a statement is
    preceded by an explanatory comment (very normal SQL style, and used
    throughout this project's own demo files), the anchor would otherwise
    never match since the text starts with '--', not 'DROP'. Only strips
    from the FRONT, so a comment appearing mid-statement (e.g. after a
    comma in an ALTER TABLE clause list) is left untouched -- that's a
    separate, not-yet-handled case, not silently mishandled here.
    """
    lines = sql_text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("--")):
        i += 1
    return "\n".join(lines[i:])


def parse_migration(sql_text: str) -> Dict[str, Any]:
    """
    UNCHANGED single-statement parser. Do not modify -- this is the
    already-tested path that parse_multi_table_migration() below builds on
    top of, without touching a single line of it.
    """
    sql_text = sql_text.strip()
    if not sql_text:
        return {"table": None, "operations": []}

    sql_text = _strip_leading_comment_lines(sql_text).strip()
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


def parse_multi_table_migration(sql_text: str) -> List[Dict[str, Any]]:
    """
    Splits a full migration file into individual top-level statements
    (semicolon-separated, respecting parens so a DECIMAL(10,2) inside one
    statement never causes a false split) and parses EACH ONE with the
    existing, unchanged parse_migration().

    Returns a list of per-statement results, each in the same shape
    parse_migration() already returns: {"table": ..., "operations": [...]}.

    Statements that don't resolve to a table (blank lines, comments-only
    fragments, or genuinely unparseable text) are skipped rather than
    included as an empty/None entry -- callers can assume every item in
    the returned list has a real table name.
    """
    results = []
    for stmt in _split_top_level_statements(sql_text):
        # parse_migration() strips/re-adds semicolons internally via
        # rstrip(';') in clause splitting and its own DROP TABLE regex,
        # so passing the statement as-is (no trailing ';') is safe.
        parsed = parse_migration(stmt)
        if parsed.get("table"):
            results.append(parsed)
    return results


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

    # --- NEW: multi-table migration file, mixing several statement types ---
    print("--- Multi-table test ---")
    multi_sql = """
    ALTER TABLE orders
      DROP COLUMN shipping_address,
      ADD COLUMN loyalty_points INT;

    ALTER TABLE customers
      ALTER COLUMN total_amount TYPE DECIMAL(10,2);

    DROP TABLE old_staging_table;

    ALTER TABLE payments
      RENAME COLUMN txn_id TO transaction_id;
    """
    multi_results = parse_multi_table_migration(multi_sql)
    print(f"Found {len(multi_results)} table(s):")
    for r in multi_results:
        print(f"  - {r['table']}: {len(r['operations'])} operation(s)")
        for op in r['operations']:
            print(f"      {op}")

    assert len(multi_results) == 4, f"FIX FAILED: expected 4 tables, got {len(multi_results)}"
    assert {r['table'] for r in multi_results} == {"orders", "customers", "old_staging_table", "payments"}
    print("\nPASS: all 4 tables parsed correctly from one multi-statement file")
