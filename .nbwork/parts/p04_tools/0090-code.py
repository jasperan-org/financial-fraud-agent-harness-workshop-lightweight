from workshop import tools as wt

TOOLS, ALWAYS_ON_TOOLS, register = wt.make_registry(agent_conn, ONNX_EMBED_MODEL)   # TOOLS: name -> (callable, schema)

# Closest tools first: VECTOR_DISTANCE between each tool's stored embedding and the embedding the database
# computes for the text bound as :q. Returns (name, description) for the first :n rows only.
_TOOL_SQL = ("SELECT name, description FROM toolbox ORDER BY VECTOR_DISTANCE(embedding, "
             f"VECTOR_EMBEDDING({ONNX_EMBED_MODEL} USING :q AS DATA), COSINE) FETCH FIRST :n ROWS ONLY")

def retrieve_tools(query, k=6):
    """Schemas of the k tools closest to the query, plus the always-on tools."""
    with agent_conn.cursor() as cur:
        # TODO 5 (two lines): (a) run _TOOL_SQL on `cur`, binding :q to the query text and :n to 4 times k
        #   (we fetch extra candidates so the reranker has something to choose from).
        # (b) best = rerank(query, rows, top_k=k, content_key="content"): `rows` is the list built below,
        #   top_k is how many to keep, content_key names the dict key holding the text to compare.
        #   `best` is a list of the k best row dicts, most relevant first.
        cur.execute(_TOOL_SQL, q=query, n=k * 4)
        rows = [{"name": n, "content": wt.lob_text(d)} for n, d in cur]   # [{"name": ..., "content": text}, ...]
    best = rerank(query, rows, top_k=k, content_key="content")
    # Names of the best tools, then the always-on ones; dict.fromkeys drops duplicates and keeps order.
    # Return the schema (index 1 of the TOOLS entry) of each name that is registered.
    return [TOOLS[n][1] for n in dict.fromkeys([r["name"] for r in best] + sorted(ALWAYS_ON_TOOLS)) if n in TOOLS]
