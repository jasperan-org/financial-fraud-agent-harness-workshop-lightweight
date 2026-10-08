# TODO 4: implement retrieve_knowledge
from workshop.retrieval import to_hit

def retrieve_knowledge(query: str, k: int = 5,
                       kinds: list[str] | None = None) -> list[dict]:
    """Vector search over AML_KNOWLEDGE_VS, reranked.

    Steps:
    1. An LLM may pass kinds as one "a,b" string: split it. Filter is {"kind": {"$in": kinds}}, or None.
    2. knowledge_vs.similarity_search_with_score(query, k=k * 4, filter=...) -> (Document, distance) pairs.
    3. to_hit(doc, distance=float(dist)) turns each pair into a hit dict.
    4. Return rerank(query, hits, top_k=k, content_key="body").
    """
    # YOUR CODE HERE
    raise NotImplementedError("TODO 4: retrieve_knowledge")
