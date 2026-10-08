# TODO 5: implement hybrid_search_knowledge
from langchain_oracledb import OracleTextSearchRetriever
from workshop.retrieval import keyword_terms

def hybrid_search_knowledge(query: str, k: int = 5, rrf_k: int = 60) -> list[dict]:
    """Vector leg + Oracle Text leg, fused with Reciprocal Rank Fusion.

    Steps:
    1. vec = Documents from knowledge_vs.similarity_search_with_score(query, k=30);
       txt = OracleTextSearchRetriever(vector_store=knowledge_vs, k=30).invoke(keyword_terms(query)).
    2. For each leg ("vec_rank", "txt_rank") and each Document at rank 1, 2, ...: take
       fused[doc.id] = to_hit(doc, rrf_score=0.0, vec_rank=None, txt_rank=None), set hit[leg] = rank,
       add 1 / (rrf_k + rank) to hit["rrf_score"].
    3. Return the hits by rrf_score, highest first, cut to k.
    """
    # YOUR CODE HERE
    raise NotImplementedError("TODO 5: hybrid_search_knowledge")
