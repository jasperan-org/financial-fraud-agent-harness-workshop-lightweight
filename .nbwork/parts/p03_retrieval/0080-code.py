# Hard-stop checkpoint: TODO 4
_q = "how are transaction amounts stored"
_hits = retrieve_knowledge(_q, k=3, kinds="column")
assert _hits, "❌ TODO 4: retrieve_knowledge returned no hits."
assert {"kind", "subject", "body", "metadata", "distance"} <= _hits[0].keys(), "❌ TODO 4: each hit needs kind, subject, body, metadata, distance."
assert all(h["kind"] == "column" for h in _hits), "❌ TODO 4: the kinds filter was not applied."
assert len(_hits) <= 3, "❌ TODO 4: return at most k hits."
_two = retrieve_knowledge(_q, k=6, kinds="column,policy")
assert _two and {h["kind"] for h in _two} <= {"column", "policy"}, "❌ TODO 4: 'a,b' must split into two kinds."
_pol = retrieve_knowledge("structuring cash deposits below the reporting threshold", k=3, kinds=["policy"])
assert _pol and all(h["kind"] == "policy" for h in _pol), "❌ TODO 4: kinds may also be a list."
assert len(retrieve_knowledge(_q, k=3)) == 3, "❌ TODO 4: without kinds, return k hits from every kind."
assert len(retrieve_knowledge(_q, k=1)) == 1, "❌ TODO 4: k=1 must return exactly one hit."
print("✅ TODO 4 passed: retrieve_knowledge filters by kind and returns at most k hits.")
