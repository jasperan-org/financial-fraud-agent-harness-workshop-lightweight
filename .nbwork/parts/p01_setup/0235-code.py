from workshop.llm import make_chat

llm, chat = make_chat(LLM_PROVIDER, LLM_MODEL, OCI_ROTATOR, OCI_ENDPOINT, OCI_COMPARTMENT_ID)
