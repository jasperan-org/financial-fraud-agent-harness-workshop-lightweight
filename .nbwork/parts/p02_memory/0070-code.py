from workshop.memory import find_memory

# Hard-stop checkpoint: TODO 2
_subject = "FINANCE.TRANSACTIONS.AMOUNT_CENTS"
_query = "monetary denomination scale"
if not find_memory(memory_client, USER_ID, AGENT_ID, "column", _subject):   # add once, even if re-run
    memory_client.add_memory(
        "Table FINANCE.TRANSACTIONS column AMOUNT_CENTS: amounts are stored in USD CENTS, never dollars.",
        user_id=USER_ID, agent_id=AGENT_ID, metadata={"kind": "column", "subject": _subject})
_hits = recall_memories(_query, k=3, kind="column")
assert _hits, "❌ TODO 2: recall_memories returned nothing. Did you pass user_id, agent_id and max_results=k?"
assert all({"id", "kind", "subject", "body", "distance"} <= set(h) for h in _hits), \
    "❌ TODO 2: each hit needs the keys id, kind, subject, body, distance."
assert all(h["kind"] == "column" and h["body"] for h in _hits), "❌ TODO 2: kind and body must come from the hit."
assert any(h["subject"] == _subject for h in _hits), "❌ TODO 2: the stored memory did not come back."
assert len(recall_memories(_query, k=1, kind="column")) == 1, "❌ TODO 2: k must be passed as max_results."
assert recall_memories(_query, k=3, kind="no_such_kind") == [], "❌ TODO 2: kind must filter on metadata."
print(f"   top hit: d={_hits[0]['distance']:.4f}  {_hits[0]['subject']}")
print("✅ TODO 2 passed: recalled the stored memory by meaning.")
