import sqlparse
from sqlparse.sql import IdentifierList, Identifier
from sqlparse.tokens import Keyword, DDL

def parse_migration(sql_text):
    parsed = sqlparse.parse(sql_text)[0]
    tokens = [t for t in parsed.tokens if not t.is_whitespace]

    result = {"table": None, "operations": []}

    # Find table name (after ALTER TABLE)
    for i, token in enumerate(tokens):
        if token.ttype is Keyword and token.value.upper() == "TABLE":
            # next non-whitespace token is the table name
            result["table"] = str(tokens[i + 1]).strip()
            break

    # Find operations: ADD COLUMN / DROP COLUMN / ALTER COLUMN
    raw = sql_text.upper()
    if "ADD COLUMN" in raw:
        result["operations"].append("ADD")
    if "DROP COLUMN" in raw:
        result["operations"].append("DROP")
    if "ALTER COLUMN" in raw or ("TYPE" in raw and "ALTER" in raw):
        result["operations"].append("TYPE_CHANGE")

    return result


# --- Test cases ---
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

for i, sql in enumerate([test_1, test_2, test_3], 1):
    print(f"--- Test {i} ---")
    print(parse_migration(sql))
    print()