from functools import partial

# Closest skills first (same idea as _TOOL_SQL): :q is the search text, :k how many rows to return.
_SKILL_SQL = ("SELECT name, category, description FROM skillbox ORDER BY VECTOR_DISTANCE(embedding, "
              f"VECTOR_EMBEDDING({ONNX_EMBED_MODEL} USING :q AS DATA), COSINE) FETCH FIRST :k ROWS ONLY")

@register
def tool_list_skills(query: str, k: int = 5) -> str:
    """Search the skillbox semantically. Returns top-k skills (name + description)."""
    with agent_conn.cursor() as cur:
        # TODO 7 (two lines): (a) run _SKILL_SQL on `cur`, binding :q to query and :k to k.
        # (b) hits = a list with one dict per row, in row order, each {"name": ..., "category": ..., "description": ...};
        #     rows are (name, category, description) tuples, and wt.lob_text(description) turns the CLOB into a str.
        raise NotImplementedError("TODO 7: run _SKILL_SQL with q=query, k=k")
        hits = ...  # TODO 8b: list of {"name", "category", "description"} dicts
    return json.dumps(hits)   # JSON text of the list, best match first

build_skill_manifest = partial(wt.skill_manifest, agent_conn, ONNX_EMBED_MODEL)   # build_skill_manifest(query, k=3)
