from workshop import tools as wt

TOOLS, ALWAYS_ON_TOOLS, register = wt.make_registry(agent_conn, ONNX_EMBED_MODEL)   # TOOLS: name -> (callable, schema)

# TODO 6: implement retrieve_tools(query, k=6) -> list of tool schemas
def retrieve_tools(query, k=6):
    """Schemas of the k tools closest to the query, plus the always-on tools.

    Steps:
    1. Select name, description from toolbox ordered by
       VECTOR_DISTANCE(embedding, VECTOR_EMBEDDING(<ONNX_EMBED_MODEL> USING :q AS DATA), COSINE),
       first k * 4 rows. wt.lob_text(description) turns a CLOB into str.
    2. rerank(query, [{"name": ..., "content": text}, ...], top_k=k, content_key="content").
    3. Return TOOLS[name][1] for the reranked names plus ALWAYS_ON_TOOLS, once each, only names in TOOLS.
    """
    # YOUR CODE HERE
    raise NotImplementedError("TODO 6: retrieve_tools")
