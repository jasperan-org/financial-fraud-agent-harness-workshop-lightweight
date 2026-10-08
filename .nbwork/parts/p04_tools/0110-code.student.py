import json
import re

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# TODO 7: implement tool_run_sql (keep the @register)
# Returns a JSON string: {"columns": [...], "rows": [[...]], "row_count": N}, or {"error": "..."}.
# Steps:
# 1. Reject a statement that _READ_ONLY does not match (after sql.strip()) with an error JSON.
# 2. Execute it on agent_conn.cursor() and return wt.rows_json(cur, max_rows).
# 3. Catch any database error and return it as {"error": str(e)}.
@register
def tool_run_sql(sql: str, max_rows: int = 50) -> str:
    """Execute a READ-ONLY SQL statement (SELECT/WITH only) against the Oracle AI Database and return up to `max_rows` rows as JSON."""
    # YOUR CODE HERE
    raise NotImplementedError("TODO 7: tool_run_sql")
