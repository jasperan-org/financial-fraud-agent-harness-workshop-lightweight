import json
import re

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# TODO 7: implement tool_run_sql (keep the @register)
@register
def tool_run_sql(sql: str, max_rows: int = 50) -> str:
    """Execute a READ-ONLY SQL statement (SELECT/WITH only) against the Oracle AI Database and return up to `max_rows` rows as JSON."""
    if not _READ_ONLY.match(sql.strip()):
        return json.dumps({"error": "only SELECT / WITH statements are allowed in run_sql"})
    try:
        with agent_conn.cursor() as cur:
            cur.execute(sql)
            return wt.rows_json(cur, max_rows)
    except Exception as e:
        return json.dumps({"error": str(e)})
