from langchain_oracledb.retrievers.text_search import create_text_index
from langchain_oracledb.vectorstores.oraclevs import create_index
from workshop.retrieval import TEXT_INDEX, make_reranker, mirror_writes

create_index(agent_conn, knowledge_vs, params={"idx_name": "AML_KNOWLEDGE_HNSW", "idx_type": "HNSW"})
create_text_index(agent_conn, TEXT_INDEX, vector_store=knowledge_vs)   # used by 3.3
rerank = make_reranker(agent_conn)   # in-DB cross-encoder; keeps the vector order if none is loaded
scanner.write_facts = mirror_writes(scanner.write_facts, knowledge_vs, memory_client, USER_ID, AGENT_ID)
write_facts = scanner.write_facts    # run_scan calls scanner.write_facts, so scans update the store too
print("HNSW and Oracle Text indexes ready; fact writes now also update AML_KNOWLEDGE_VS")
