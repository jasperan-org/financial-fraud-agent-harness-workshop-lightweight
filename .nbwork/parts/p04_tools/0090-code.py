from workshop import tools as wt

TOOLS, ALWAYS_ON_TOOLS, register = wt.make_registry(agent_conn, ONNX_EMBED_MODEL)   # TOOLS: name -> (callable, schema)

# TODO 6: implement retrieve_tools(query, k=6) -> list of tool schemas
def retrieve_tools(query, k=6):
    """Schemas of the k tools closest to the query, plus the always-on tools."""
    with agent_conn.cursor() as cur:
        cur.execute("SELECT name, description FROM toolbox ORDER BY VECTOR_DISTANCE(embedding, "
                    f"VECTOR_EMBEDDING({ONNX_EMBED_MODEL} USING :q AS DATA), COSINE) FETCH FIRST :n ROWS ONLY", q=query, n=k * 4)
        rows = [{"name": n, "content": wt.lob_text(d)} for n, d in cur]
    best = rerank(query, rows, top_k=k, content_key="content")
    return [TOOLS[n][1] for n in dict.fromkeys([r["name"] for r in best] + sorted(ALWAYS_ON_TOOLS)) if n in TOOLS]
