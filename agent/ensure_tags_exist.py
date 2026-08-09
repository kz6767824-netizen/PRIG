"""
agent/ensure_tags_exist.py

FIX: now accepts an optional `tag_names` argument -- ensures only the
requested tag(s), not all four every time. Calling with no argument still
ensures everything (useful for a one-time setup step), but write_back_tag()
now passes only the ONE tag it's about to apply, since that's all it ever
actually needs.
"""

from typing import Optional, List

from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import TagPropertiesClass
from datahub.metadata.urns import TagUrn

ALL_TAG_DESCRIPTIONS = {
    "pending-review-breaking": "Pending schema change classified as BREAKING by koza",
    "pending-review-critical": "Pending schema change classified as CRITICAL by koza",
    "pending-review": "Legacy generic pending-review tag",
    "PII": "Column contains personally identifiable information",
}


def ensure_tags_exist(
    tag_names: Optional[List[str]] = None,
    server: str = "http://localhost:8081",
    token: str = "",
):
    """
    Creates (or updates) only the requested tag(s). If tag_names is None,
    ensures ALL known tags -- intended for a one-time manual setup call,
    not for routine use inside write_back_tag().

    Unknown tag names (not in ALL_TAG_DESCRIPTIONS) are skipped with a
    warning rather than silently ignored or given a blank description.
    """
    names_to_ensure = tag_names if tag_names is not None else list(ALL_TAG_DESCRIPTIONS.keys())

    emitter = DatahubRestEmitter(server, token)
    for tag_name in names_to_ensure:
        description = ALL_TAG_DESCRIPTIONS.get(tag_name)
        if description is None:
            print(f"[ensure_tags_exist] WARNING: '{tag_name}' has no known "
                  f"description -- skipping (add it to ALL_TAG_DESCRIPTIONS "
                  f"if this is intentional).")
            continue
        try:
            tag_urn = TagUrn(tag_name)
            aspect = TagPropertiesClass(name=tag_name, description=description)
            mcpw = MetadataChangeProposalWrapper(entityUrn=str(tag_urn), aspect=aspect)
            emitter.emit(mcpw)
            print(f"[ensure_tags_exist] Ensured tag exists: {tag_name}")
        except Exception as e:
            print(f"[ensure_tags_exist] FAILED for tag '{tag_name}': {type(e).__name__}: {e}")


if __name__ == "__main__":
    print("--- Ensuring ALL tags (manual one-time setup) ---")
    ensure_tags_exist()
    print()
    print("--- Ensuring only ONE tag (what write_back_tag now does) ---")
    ensure_tags_exist(tag_names=["pending-review-breaking"])
