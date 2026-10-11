import json
import re

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

@register
def tool_run_sql(sql: str, max_rows: int = 50) -> str:
    """Execute a READ-ONLY SQL statement (SELECT/WITH only) against the Oracle AI Database and return up to `max_rows` rows as JSON."""
    # TODO 6 (three lines, two spots):
    # (a) Here: if _READ_ONLY.match(sql.strip()) finds no match, return json.dumps({"error": "<short message>"}).
    # (b) Inside the `with` below: run `sql` on `cur`, then return wt.rows_json(cur, max_rows),
    #     which gives a JSON string {"columns": [...], "rows": [[...]], "row_count": N}.
    try:
        with agent_conn.cursor() as cur:
            raise NotImplementedError("TODO 6: run the SQL and return wt.rows_json(cur, max_rows)")
    except Exception as e:   # any database error goes back to the agent as JSON
        return json.dumps({"error": str(e)})
