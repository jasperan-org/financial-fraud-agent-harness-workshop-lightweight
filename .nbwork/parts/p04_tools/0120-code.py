# Hard-stop checkpoint: TODO 7
assert "run_sql" in TOOLS, "❌ TODO 7: keep the @register decorator."
_out = json.loads(tool_run_sql("SELECT level AS n FROM dual CONNECT BY level <= 5", max_rows=2))
assert _out.get("columns") == ["N"] and _out.get("row_count") == 2, f"❌ TODO 7: return the columns and at most max_rows rows, got {_out}."
assert json.loads(tool_run_sql("WITH t AS (SELECT 1 AS x FROM dual) SELECT x FROM t")).get("row_count") == 1, "❌ TODO 7: WITH statements must run."
assert "error" in json.loads(tool_run_sql("DROP TABLE x")), "❌ TODO 7: the read-only guard let a DROP through."
assert "error" in json.loads(tool_run_sql("SELECT * FROM no_such_table_xyz")), "❌ TODO 7: a database error must come back as {\"error\": ...}."
print("✅ TODO 7 passed: tool_run_sql is registered, read-only and returns JSON.")
