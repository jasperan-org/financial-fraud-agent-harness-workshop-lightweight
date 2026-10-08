from oci_key_rotation import make_rotating_oamp_llm
from oracleagentmemory.core import OracleAgentMemory, MemoryExtractionConfig
from oracleagentmemory.core.embedders import OracleDBEmbedder
from oracleagentmemory.core.llms import Llm

ONNX_EMBED_MODEL = "ALL_MINILM_L12_V2"
extraction_llm = (make_rotating_oamp_llm(LLM_MODEL, OCI_ENDPOINT, OCI_ROTATOR)
                  if LLM_PROVIDER == "oci" else Llm(LLM_MODEL))

memory_client = OracleAgentMemory(
    connection=agent_conn, llm=extraction_llm, memory_store_id="EDA_ONNX",
    embedder=OracleDBEmbedder(agent_conn, model=ONNX_EMBED_MODEL, embedding_dimension=384),
    memory_extraction_config=MemoryExtractionConfig(extract_memories=True),
    schema_policy="create_if_necessary")
