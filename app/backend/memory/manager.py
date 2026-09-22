"""OAMP-backed memory layer. Mirrors §4.1 of the notebook: the OracleAgentMemory
client owns memories/threads/context-cards; we add a custom in-DB ONNX embedder.

The whole agent reads/writes memory through this module so the API surface is
small and stable.

OAMP 26.8 adds database-native Deep Data Security for this store
(`oracleagentmemory.core.deepsec`): `db/deep_security.py` installs the
UserOwnRows + GlobalMemories policies on a Deep Sec-capable database and
`docs/part-8-deep-data-security.md` walks through the runtime context.
"""

from __future__ import annotations

import numpy as np

import os

from oracleagentmemory.core import OracleAgentMemory
from oracleagentmemory.core.llms import Llm
from oracleagentmemory.apis.embedders.embedder import IEmbedder

from config import (
    AGENT_ID, USER_ID,
    LLM_FALLBACK_MODEL, LLM_MODEL, LLM_PROVIDER,
    OCI_GENAI_API_KEY, OCI_GENAI_ENDPOINT,
    ONNX_EMBED_DIM, ONNX_EMBED_MODEL,
    OPENAI_API_KEY,
)

# OAMP >= 26.6 names the managed DB objects from `memory_store_id`; the older
# `table_name_prefix` is deprecated and removed in 27.1. "EDA_ONNX" resolves to
# the same EDA_ONNX_MEMORY / EDA_ONNX_THREAD / ... tables the workshop has used
# since 26.4 — the store ID is joined to object names with an underscore.
MEMORY_STORE_ID = "EDA_ONNX"


class OracleONNXEmbedder(IEmbedder):
    """Routes embedding through Oracle's in-DB ONNX model (§3.4 of the notebook).
    Same connection the OAMP client uses → no network round-trip, no extra keys.
    """

    def __init__(self, conn, model_name: str = ONNX_EMBED_MODEL, dim: int = ONNX_EMBED_DIM):
        self._conn = conn
        self._model = model_name
        self._dim = dim

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        sql = f"SELECT VECTOR_EMBEDDING({self._model} USING :t AS DATA) FROM dual"
        with self._conn.cursor() as cur:
            for i, t in enumerate(texts):
                cur.execute(sql, t=t)
                vec = cur.fetchone()[0]
                out[i] = np.asarray(list(vec), dtype=np.float32)
        return out

    async def embed_async(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        return self.embed(texts, is_query=is_query)


def build_extraction_llm():
    """LLM used by OAMP for memory extraction + context-summary refresh.

    Mirrors agent/llm.py's OCI-first / OpenAI-fallback policy: try OCI when
    LLM_PROVIDER=oci and credentials are present, otherwise (or on init
    failure) build an OpenAI client on `LLM_FALLBACK_MODEL` (gpt-5.5).
    Returns None if neither is available — caller disables extraction.
    """
    if LLM_PROVIDER == "oci" and OCI_GENAI_API_KEY and OCI_GENAI_ENDPOINT:
        try:
            llm = Llm(
                f"openai/{LLM_MODEL}",
                api_base=OCI_GENAI_ENDPOINT,
                api_key=OCI_GENAI_API_KEY,
            )
            print(f"[memory] OAMP extraction LLM = OCI {LLM_MODEL} @ {OCI_GENAI_ENDPOINT}")
            return llm
        except Exception as e:
            print(f"[memory] OCI extraction LLM init failed: "
                  f"{type(e).__name__}: {e}; falling back to OpenAI {LLM_FALLBACK_MODEL}.")

    if OPENAI_API_KEY:
        # litellm reads OPENAI_API_KEY from os.environ. Make sure it's set
        # even if the .env loader stashed it only on os.environ via dotenv.
        os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY)
        print(f"[memory] OAMP extraction LLM = OpenAI {LLM_FALLBACK_MODEL}")
        return Llm(LLM_FALLBACK_MODEL)

    print("[memory] No usable LLM credentials — OAMP extraction DISABLED.")
    return None


def build_memory_client(agent_conn) -> OracleAgentMemory:
    """The single OAMP client used by the loop and the API.

    If no LLM is available we still build the client (for memory storage and
    semantic retrieval), but disable auto-extraction so OAMP doesn't hit a
    None LLM during add_messages.
    """
    extraction_llm = build_extraction_llm()
    client = OracleAgentMemory(
        connection=agent_conn,
        embedder=OracleONNXEmbedder(agent_conn),
        llm=extraction_llm,
        extract_memories=(extraction_llm is not None),
        schema_policy="create_if_necessary",
        memory_store_id=MEMORY_STORE_ID,
    )
    for register_fn, eid, info in [
        (client.add_user, USER_ID, "Operator querying the enterprise database in natural language."),
        (client.add_agent, AGENT_ID, "Data agent grounded in scanned schema metadata."),
    ]:
        try:
            register_fn(eid, info)
        except ValueError as e:
            if "already exists" not in str(e):
                raise
    return client


def get_or_create_thread(client: OracleAgentMemory, thread_id: str):
    """Return the OAMP thread for a harness-level id, creating it on first use."""
    try:
        return client.get_thread(thread_id)
    except Exception:
        return client.create_thread(
            thread_id=thread_id,
            user_id=USER_ID,
            agent_id=AGENT_ID,
            enable_context_summary=True,
        )


# --------------------------------------------------------------------------- #
# Memory relations (OAMP >= 26.8)
# --------------------------------------------------------------------------- #
# A relation is a directed edge between two stored memories. The type decides
# what OAMP's lifecycle engine does to the *target* memory, which is the part
# that surprises people:
#
#   supersedes   target -> INVALID  ("Superseded by another memory.")
#   refines      target -> INVALID  ("Refined by another memory.")
#   duplicates   target -> INVALID  ("Duplicated by another memory.")
#   contradicts  both stay VALID    (the conflict is the point)
#   supports     both stay VALID    (evidence, not replacement)
#
# Default searches hide INVALID memories; link traversal still returns them, so
# `search(..., num_hops=1)` is how history stays reachable after a correction.

LINK_TYPES = ("supersedes", "contradicts", "refines", "supports", "duplicates")
INVALIDATING_LINK_TYPES = ("supersedes", "refines", "duplicates")


def link_memories(
    client: OracleAgentMemory,
    source_id: str,
    target_id: str,
    link_type: str = "supersedes",
    metadata: dict | None = None,
) -> str | None:
    """Create one directed relation `source -link_type-> target`.

    Returns the relation id. OAMP stores one orientation per endpoint pair, so
    re-creating an existing relation returns its id instead of raising. For the
    invalidating types above, this also retires the target memory.
    """
    if link_type not in LINK_TYPES:
        raise ValueError(f"link_type must be one of {LINK_TYPES}, got {link_type!r}")
    store = client._store
    try:
        ids = store.add_relations(
            source_record_ids=source_id,
            source_record_types="memory",
            target_record_ids=target_id,
            target_record_types="memory",
            relation_types=link_type,
            metadata=metadata or {},
        )
        return ids[0] if ids else None
    except Exception as e:
        # Most likely the pair already has this relation (one orientation per
        # endpoint pair). Confirm that before reporting a failure.
        try:
            existing = store.get_relation(
                source_id, "memory", target_id, "memory", link_type
            )
            if existing is not None:
                return existing.id
        except Exception:
            pass
        print(
            f"[memory] link {str(source_id)[:8]} -{link_type}-> "
            f"{str(target_id)[:8]} failed: {type(e).__name__}: {e}"
        )
        return None


def find_memory(client: OracleAgentMemory, ref: str):
    """Resolve a memory id or a free-text phrase to one memory record.

    Exact ids are looked up directly; anything else is semantically searched
    with the same scope the agent's knowledge retrieval uses, valid memories
    only. Returns a MemoryRecord or None.
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    if len(ref) >= 32 and "-" in ref:
        try:
            record = client._store.get("memory", ref)
            if record is not None:
                return record
        except Exception:
            pass
    hits = client.search(
        query=ref,
        user_id=USER_ID,
        agent_id=AGENT_ID,
        max_results=1,
        include_invalid_results=False,
    )
    if not hits:
        return None
    return getattr(hits[0], "record", None)


def _link_view(store, other_id: str, relation: str, direction: str) -> dict:
    """The far end of a relation, rendered for the tool/pane output."""
    record = None
    try:
        record = store.get("memory", other_id)
    except Exception:
        pass
    meta = (getattr(record, "metadata", None) or {}) if record else {}
    body = getattr(record, "content", "") if record else ""
    if hasattr(body, "read"):
        body = body.read()
    return {
        "relation": relation,
        "direction": direction,
        "memory_id": other_id,
        "kind": meta.get("kind", "memory"),
        "subject": meta.get("subject", ""),
        "status": str(getattr(record, "status", "")).split(".")[-1],
        "body": str(body)[:300],
    }


def memory_links(
    client: OracleAgentMemory, memory_id: str, limit: int = 10
) -> list[dict]:
    """Relations touching a memory, normalised so the label reads from here.

    A memory that supersedes another reports `relation='supersedes'`,
    `direction='out'`; the superseded one reports `relation='is_superseded_by'`,
    `direction='in'`. Traversal follows links in either direction, matching
    `search(..., num_hops=N)`.
    """
    store = client._store
    out: list[dict] = []
    try:
        outgoing = store.list_relations(source_record_id=memory_id, limit=limit) or []
    except Exception:
        outgoing = []
    try:
        incoming = store.list_relations(target_record_id=memory_id, limit=limit) or []
    except Exception:
        incoming = []
    for rel in outgoing:
        out.append(_link_view(store, rel.target_record_id, rel.relation_type, "out"))
    for rel in incoming:
        label = rel.opposite_relation_type or rel.relation_type
        out.append(_link_view(store, rel.source_record_id, label, "in"))
    return out[:limit]
