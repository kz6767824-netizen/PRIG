"""
test_llm_real.py

Unlike llm_explanation.py's own __main__ block (which deliberately clears
GROQ_API_KEY to test the fallback path), this script does NOT touch the
environment variable at all -- it uses whatever is actually set, so this
is the real test of whether your Groq key and API call work.
"""

import sys
import os

AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent")
sys.path.insert(0, AGENT_DIR)
from llm_explanation import llm_explanation

key_present = "GROQ_API_KEY" in os.environ
print(f"GROQ_API_KEY detected in environment: {key_present}")
if not key_present:
    print("No key found -- run 'setx GROQ_API_KEY \"your-key\"' in a NEW terminal first.")
print()

result = llm_explanation(
    table="orders",
    column="shipping_address",
    operation="DROP",
    severity="Breaking",
    downstream_assets=[{"name": "daily_revenue_dashboard", "type": "DATASET"}],
    is_pii=False,
)
print("--- Result ---")
print(result)
