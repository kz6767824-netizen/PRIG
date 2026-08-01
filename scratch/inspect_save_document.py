import inspect

try:
    from datahub_agent_context.mcp_tools import save_document
    print("=== signature ===")
    print(inspect.signature(save_document))
    print()
    print("=== docstring ===")
    print(save_document.__doc__)
except ImportError as e:
    print(f"Could not import save_document: {e}")
    print("Trying to find it under a different name...")
    import datahub_agent_context.mcp_tools as tools
    print([name for name in dir(tools) if "doc" in name.lower()])