from functools import partial

# TODO 8: implement tool_list_skills (keep the @register)
@register
def tool_list_skills(query: str, k: int = 5) -> str:
    """Search the skillbox semantically. Returns top-k skills (name + description)."""
    with agent_conn.cursor() as cur:
        cur.execute("SELECT name, category, description FROM skillbox ORDER BY VECTOR_DISTANCE(embedding, "
                    f"VECTOR_EMBEDDING({ONNX_EMBED_MODEL} USING :q AS DATA), COSINE) FETCH FIRST :k ROWS ONLY", q=query, k=k)
        hits = [{"name": n, "category": c, "description": wt.lob_text(d)} for n, c, d in cur]
    return json.dumps(hits)

build_skill_manifest = partial(wt.skill_manifest, agent_conn, ONNX_EMBED_MODEL)   # build_skill_manifest(query, k=3)
