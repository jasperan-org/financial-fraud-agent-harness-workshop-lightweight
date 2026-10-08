# Hard-stop checkpoint: TODO 3
_facts = _scan_tables(agent_conn, DEMO_USER)
with agent_conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM all_tables WHERE owner = :o", o=DEMO_USER.upper())
    _n_tables = cur.fetchone()[0]
assert _facts, "❌ TODO 3: _scan_tables returned no facts. Did you bind owner.upper() and append each Fact?"
assert all(isinstance(f, Fact) and f.kind == "table" for f in _facts), "❌ TODO 3: return Fact objects with kind='table'."
assert len(_facts) == _n_tables, "❌ TODO 3: return one Fact per table in ALL_TABLES."
_by_subject = {f.subject: f for f in _facts}
_txn = _by_subject.get(f"{DEMO_USER}.TRANSACTIONS")
assert _txn, f"❌ TODO 3: subject must be f'{{owner}}.{{table}}', e.g. {DEMO_USER}.TRANSACTIONS."
assert _txn.body.startswith(f"Table {DEMO_USER}.TRANSACTIONS."), "❌ TODO 3: body must start with 'Table {owner}.{table}.'."
assert {"owner", "table", "num_rows", "has_comment"} <= set(_txn.metadata), "❌ TODO 3: metadata needs owner, table, num_rows, has_comment."
assert ("Documented purpose:" in _txn.body) == _txn.metadata["has_comment"], "❌ TODO 3: add the purpose only when a comment exists."
assert ("Approximate row count:" in _txn.body) == (_txn.metadata["num_rows"] is not None), "❌ TODO 3: add the row count only when it is not None."
assert not any("None" in f.body for f in _facts), "❌ TODO 3: leave out parts whose value is None."
print(f"✅ TODO 3 passed: one table Fact per table in {DEMO_USER}.")
