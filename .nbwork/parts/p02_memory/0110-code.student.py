from workshop.memory import Fact, TABLES_SQL

# TODO 3: implement _scan_tables(conn, owner) -> list[Fact]
#   Steps:
#   1. cur.execute(TABLES_SQL, owner=owner.upper()) yields (table, comment, num_rows, last_analyzed).
#   2. Body: "Table {owner}.{table}." plus, only for values that are not None, "Documented purpose: {comment}",
#      "Approximate row count: {n:,}." and "Statistics last gathered at {ts}.", joined with spaces.
#   3. Return Fact("table", f"{owner}.{table}", body, {owner, table, num_rows, has_comment}) per table;
#      scan_columns in workshop/memory.py is a model.
#   Guide: docs/part-2-oamp-memory.md#todo-3-_scan_tables

def _scan_tables(conn, owner: str) -> list[Fact]:
    # YOUR CODE HERE
    raise NotImplementedError("TODO 3: _scan_tables")
