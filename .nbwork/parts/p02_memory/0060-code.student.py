# TODO 2: implement recall_memories(query, k=3, kind=None) -> list[dict]
#   Steps:
#   1. Call memory_client.search(query, user_id=USER_ID, agent_id=AGENT_ID,
#      record_types=["memory"], metadata_filter=..., max_results=k).
#   2. metadata_filter is {"kind": kind} when kind is given, otherwise None.
#   3. Return one dict per hit with keys id, kind, subject, body, distance: h.id, h.content, h.distance,
#      and kind and subject from (h.metadata or {}).get("kind") and .get("subject").
#   Guide: docs/part-2-oamp-memory.md#todo-2-recall_memories

def recall_memories(query, k=3, kind=None):
    # YOUR CODE HERE
    raise NotImplementedError("TODO 2: recall_memories")
