import os
from workshop.llm import configure_llm

LLM_PROVIDER, OCI_ROTATOR, OCI_ENDPOINT, OCI_COMPARTMENT_ID = configure_llm()
LLM_MODEL = os.environ["LLM_MODEL"]
