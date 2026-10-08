# Hard-stop checkpoint: TODO 5
import math

_h = hybrid_search_knowledge("how do customers avoid the reporting threshold by splitting cash deposits?", k=3)
assert _h and {"kind", "subject", "body", "metadata", "rrf_score", "vec_rank", "txt_rank"} <= _h[0].keys(), \
    "❌ TODO 5: each hit needs kind, subject, body, metadata, rrf_score, vec_rank, txt_rank."
assert len(_h) <= 3 and [x["rrf_score"] for x in _h] == sorted((x["rrf_score"] for x in _h), reverse=True), \
    "❌ TODO 5: return at most k hits, best fused score first."
assert any(x["kind"] == "policy" for x in _h), "❌ TODO 5: expected an AML policy note in the top 3."
assert any(x["vec_rank"] for x in _h) and any(x["txt_rank"] for x in _h), "❌ TODO 5: one leg returned nothing."
for x in _h:
    want = sum(1 / (60 + r) for r in (x["vec_rank"], x["txt_rank"]) if r)
    assert math.isclose(x["rrf_score"], want), "❌ TODO 5: rrf_score must add 1/(rrf_k + rank) for each leg that found the row."
_id = hybrid_search_knowledge("which column holds RATE_BP", k=1)[0]
assert _id["subject"].endswith("LOANS.RATE_BP"), f"❌ TODO 5: expected FINANCE.LOANS.RATE_BP first, got {_id['subject']!r}."
print("✅ TODO 5 passed: hybrid_search_knowledge fuses both legs with RRF.")
