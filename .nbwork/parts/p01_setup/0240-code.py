# TODO 1: ask the bare model a question about Meridian Bank data (no memory, retrieval or tools).

QUESTION = "Which Meridian Bank customer has the most flagged transactions in the last 30 days?"

_bare_answer = chat([{"role": "user", "content": QUESTION}]).choices[0].message.content if QUESTION.strip() else None
print("A:", (_bare_answer or "")[:300])

# Hard-stop checkpoint: TODO 1
assert QUESTION.strip(), "❌ TODO 1: set QUESTION to a question first."
assert any(w in QUESTION.lower() for w in ("meridian", "finance", "customer", "account", "transaction", "alert")), \
    "❌ TODO 1: ask about Meridian Bank data (a customer, account, transaction or alert)."
assert _bare_answer, "❌ TODO 1: the model returned no answer. Check your key and LLM_MODEL."
print("✅ TODO 1 passed: the bare model answered, with no access to the bank data.")
