# TODO 5: implement hybrid_search_knowledge
from langchain_oracledb import OracleTextSearchRetriever
from workshop.retrieval import keyword_terms

def hybrid_search_knowledge(query: str, k: int = 5, rrf_k: int = 60) -> list[dict]:
    vec = [doc for doc, _ in knowledge_vs.similarity_search_with_score(query, k=30)]
    txt = OracleTextSearchRetriever(vector_store=knowledge_vs, k=30).invoke(keyword_terms(query))
    fused = {}
    for leg, docs in (("vec_rank", vec), ("txt_rank", txt)):
        for rank, doc in enumerate(docs, start=1):
            hit = fused.setdefault(doc.id, to_hit(doc, rrf_score=0.0, vec_rank=None, txt_rank=None))
            hit[leg] = rank
            hit["rrf_score"] += 1 / (rrf_k + rank)
    return sorted(fused.values(), key=lambda h: h["rrf_score"], reverse=True)[:k]
