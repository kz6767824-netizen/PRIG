import inspect
from datahub_agent_context import mcp_tools

# List every tool that mentions "tag" in its name -- so we see what's
# actually available, rather than assuming a create/upsert function exists.
tag_related = [name for name in dir(mcp_tools) if "tag" in name.lower()]
print("=== Tools with 'tag' in the name ===")
print(tag_related)
print()

for name in tag_related:
    func = getattr(mcp_tools, name)
    if callable(func):
        print(f"--- {name} ---")
        try:
            print(inspect.signature(func))
        except (TypeError, ValueError) as e:
            print(f"(could not get signature: {e})")
        doc = func.__doc__ or ""
        # Print just the first few lines of the docstring for a quick look
        print("\n".join(doc.strip().splitlines()[:5]))
        print()