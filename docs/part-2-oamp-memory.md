# Part 2: Long-Term Memory with OAMP

## What Is Agent Memory?

An LLM has no persistent state between calls. Every inference starts from scratch. **Agent memory** is the infrastructure that gives agents the ability to remember across turns, sessions, and tasks — the institutional knowledge an analyst accumulates after months of working with a database.

In this workshop the long-term store **is** the [Oracle AI Agent Memory Package (OAMP)](https://www.oracle.com/database/ai-agent-memory/).

Instead of hand-rolling a `knowledge` / `conversation` / `tool_log` schema, we hand a connection to `OracleAgentMemory` and let it own the DDL, the embedding pipeline, and the retrieval surface.

| OAMP primitive | What it stores | Replaces |
|---|---|---|
| `memory` (via `client.add_memory`) | Durable facts — scanned schema entries, user corrections, tool outputs (with metadata). | `institutional_knowledge`, `tool_log` |
| `thread` (via `client.create_thread`) | A conversation. Holds messages and exposes a context card. | `conversation` |
| `context_card` (via `thread.get_context_card`) | Compact, query-relevant block of memories + recent turns. | The hand-rolled `build_context` |

We **do** keep one bespoke table — `scan_history`. It records *that* a scan ran, not *what was learned*. It's **procedural** memory of the agent's own actions, queried by time/owner not by meaning, so we put it in a regular indexed table rather than OAMP.

## How OAMP Is Wired Up

The setup cell wires OAMP with three things you'll see referenced in the Python code (the embedder is implemented in TODO 2, defined just above it):

```python
memory_client = OracleAgentMemory(
    connection=agent_conn,                            # AGENT-owned schema
    embedder=OracleONNXEmbedder(agent_conn),          # in-DB ONNX from §1 — no network
    llm=extraction_llm,                               # same chat provider/model as §1
    memory_extraction_config=MemoryExtractionConfig(extract_memories=True),  # mine durable facts
    schema_policy="create_if_necessary",              # OAMP owns its DDL
    memory_store_id="EDA_ONNX",                       # names the EDA_ONNX_* managed tables
)
```

Three things to notice:

1. **`agent_conn`** — OAMP-managed tables live in the `AGENT` schema, not `SYS`.
2. **`OracleONNXEmbedder`** — wraps `SELECT VECTOR_EMBEDDING(ALL_MINILM_L12_V2 USING :t AS DATA) FROM dual`. Every embed call is a SQL statement on `agent_conn`. Zero network calls for embedding.
3. **`extraction_llm`** — OAMP uses the same chat model your agent uses to extract durable memories from threads and maintain a rolling summary.

`schema_policy="create_if_necessary"` means OAMP creates `EDA_ONNX_MEMORY`, `EDA_ONNX_THREAD`, `EDA_ONNX_RECORD_CHUNKS`, etc. on first use. You never write DDL for memory tables. `memory_store_id` is the naming form OAMP >= 26.6 introduced (the older `table_name_prefix="eda_onnx_"` resolved to the same object names and is removed in 27.1). The workshop requires `oracleagentmemory>=26.8`: that release also adds database-native Deep Data Security for this store — see [Part 8](part-8-deep-data-security.md).

## TODO 2: Implement `OracleONNXEmbedder.embed`

OAMP calls the embedder on every write (`add_memory`) and every search, so this method is the vector path for all of long-term memory. The class inherits from OAMP's `IEmbedder`; only `embed` is yours, and `embed_async` delegates to it.

**Your job:** for each text, run one in-database embedding and pack the results into a float32 array of shape `(len(texts), ONNX_EMBED_DIM)`:

```sql
SELECT VECTOR_EMBEDDING(ALL_MINILM_L12_V2 USING :t AS DATA) FROM dual
```

**Solution:**

```python
    def embed(self, texts, *, is_query=False):
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        sql = f"SELECT VECTOR_EMBEDDING({self._model} USING :t AS DATA) FROM dual"
        with self._conn.cursor() as cur:
            for i, t in enumerate(texts):
                cur.execute(sql, t=t)
                out[i] = np.asarray(list(cur.fetchone()[0]), dtype=np.float32)
        return out
```

There is no network hop and no Python-side model: every vector is computed by the database, and the checkpoint at the end of the cell probes it before the memory client is built.

## OAMP user and agent IDs (auto-registered)

Every memory record OAMP stores carries a `user_id` (the operator) and an `agent_id` (which agent wrote it). The pre-built `build_memory_client` call in the notebook (`memory_client = OracleAgentMemory(...)`) registers these IDs idempotently — you don't need a separate registration step. The IDs `enterprise-operator` and `enterprise-data-agent` are wired through the rest of the harness.

## The Schema Scanner: Catalog Views as Training Data

Tables are storage. **Retrieval** is what makes them useful. The agent's "enterprise awareness" comes from a scanner that reads Oracle's catalog views and converts each fact into a natural-language entry that goes into OAMP, embedded and ready for semantic retrieval.

We mine **four** sources:

1. **Structural** — `ALL_TABLES`, `ALL_TAB_COLUMNS`: names, types, nullability. *What shapes exist.*
2. **Annotation** — `ALL_TAB_COMMENTS`, `ALL_COL_COMMENTS`: human-written descriptions. *What a domain expert said.*
3. **Relational** — `ALL_CONSTRAINTS`, `ALL_CONS_COLUMNS`: PK/FK. *How tables relate.*
4. **Workload** — `V$SQL`: a sample of recent queries. *How the database is actually used.*

> **Why store scanned facts as *text* with embeddings, not as normalized rows?** Because the agent retrieves by *meaning*, not by primary key. When the user asks "which table records card transactions?" we want a cosine search over embedded descriptions to surface `FINANCE.TRANSACTIONS`, not a JOIN through four catalog views.

Each scanner helper takes `(conn, owner)` and returns a `list[Fact]`:

```python
@dataclass
class Fact:
    kind: str        # "table" | "column" | "relationship" | "query_pattern"
    subject: str     # e.g. "FINANCE.TRANSACTIONS"
    body: str        # natural-language sentence the embedder will read
    metadata: dict   # owner, table, column, etc.
```

## TODO 3: Implement `_scan_tables`

This is the simplest of the four scanners — and it's the right place to learn the pattern. It mines `ALL_TABLES` joined with `ALL_TAB_COMMENTS` and emits one `Fact(kind="table")` per table.

**The query you need to run:**

```sql
SELECT t.table_name, tc.comments, t.num_rows, t.last_analyzed
  FROM all_tables t
  LEFT JOIN all_tab_comments tc
    ON tc.owner = t.owner AND tc.table_name = t.table_name
 WHERE t.owner = :owner
 ORDER BY t.table_name
```

**For each row**, build a natural-language `body` that the embedder can index:

> `"Table FINANCE.TRANSACTIONS. Documented purpose: Card/account transactions. Approximate row count: 23606. Statistics last gathered at 2026-05-09 12:34:00."`

Concatenate the parts conditionally — skip the comment line if there's no comment, skip the row count if `num_rows` is `None`, etc.

**Solution:**

```python
def _scan_tables(conn, owner: str) -> list[Fact]:
    sql = (
        "SELECT t.table_name, tc.comments, t.num_rows, t.last_analyzed "
        "  FROM all_tables t "
        "  LEFT JOIN all_tab_comments tc "
        "    ON tc.owner = t.owner AND tc.table_name = t.table_name "
        " WHERE t.owner = :owner "
        " ORDER BY t.table_name"
    )
    facts: list[Fact] = []
    with conn.cursor() as cur:
        cur.execute(sql, owner=owner.upper())
        for table, comment, num_rows, last_analyzed in cur:
            body_parts = [f"Table {owner}.{table}."]
            if comment:
                body_parts.append(f"Documented purpose: {comment}")
            if num_rows is not None:
                body_parts.append(f"Approximate row count: {num_rows:,}.")
            if last_analyzed:
                body_parts.append(f"Statistics last gathered at {last_analyzed}.")
            facts.append(Fact(
                kind="table",
                subject=f"{owner}.{table}",
                body=" ".join(body_parts),
                metadata={
                    "owner": owner,
                    "table": table,
                    "num_rows": num_rows,
                    "has_comment": bool(comment),
                },
            ))
    return facts
```

The other three scanners (`_scan_columns`, `_scan_relationships`, `_scan_workload`) follow the same pattern and are pre-built — read them after you finish this TODO and notice how each one converts a different catalog view into the same `Fact` shape.

## How Facts Become Memories

After the four scanners run, the pre-built `write_facts()` function:

1. Computes `body_hash = sha256(fact.body)` — used for change detection.
2. Looks up an existing memory with the same `(kind, subject)` metadata.
3. **If absent** — calls `memory_client.add_memory(...)` (which embeds + inserts).
4. **If present and `body_hash` unchanged** — skips the embed call entirely.
5. **If present and `body_hash` changed** — updates the existing memory in place (same record id, so its links survive).
6. **After the facts are written** — `link_schema_facts()` connects them: every column fact and relationship fact links to its table fact with `supports`.

The hash check is what makes hourly re-scans free. The vast majority of calls hash-check and skip; only schema changes trigger an embed.

> **First run on a fresh seed takes a couple of minutes.** The Meridian Bank schema has 15 tables,
> ~120 columns and their relationships, so the first scan writes ~160 memories — and each new
> memory is an embed plus an extraction round-trip. Re-runs are seconds, because every body hash
> matches and the loop skips the expensive path. (The `FINANCE` world is deliberately wide: fifteen
> tables, not three, is what makes "which table holds this?" a real retrieval problem.)

## Relations and Links (OAMP >= 26.8)

Facts do not exist in isolation. OAMP 26.8 stores a **directed relation** between two memories,
and the relation type decides what happens to the target:

| Type | Target after linking | Use for |
|---|---|---|
| `supersedes` | **retired** (`INVALID`) | a correction that replaces an earlier fact |
| `refines` | **retired** (`INVALID`) | a more precise version of the same fact |
| `duplicates` | **retired** (`INVALID`) | the same fact stored twice |
| `contradicts` | stays valid | conflicting evidence you want flagged, not resolved |
| `supports` | stays valid | corroborating evidence / structural detail |

Retired memories stop appearing in normal search but stay reachable through link traversal, so
nothing is lost — and "one orientation per endpoint pair" is enforced by the store, so re-linking is
safe.

```python
# Correction: write the new fact and retire the old one in a single call.
memory_client.add_memory(
    "The STRUCTURING threshold is now $12,500.",
    user_id=USER_ID, agent_id=AGENT_ID, metadata={"kind": "correction"},
    memory_id_to_link=old_memory_id, link_type="supersedes",
    autonomous_linking=False,        # deterministic; True lets the LLM pick extra links
)

# Traversal: one hop from each direct hit, in either direction.
results = memory_client.search(
    "STRUCTURING threshold", user_id=USER_ID,
    max_results=5, num_hops=1, max_linked_results=20,
)
for r in results:
    for relation, linked in (r.linked_results or []):
        print(relation.relation_type, linked.status, linked.content)
```

`num_hops` accepts 0–5. Direct hits hide retired memories by default; the hop is what brings the
history back (`include_invalid_results=False` + `num_hops=1` = "current truth plus its provenance").

The workshop uses links in four places:

- **`remember(supersedes=...)`** — the agent corrects a fact by memory id or by phrase; the old fact
  is retired and stays visible through `search_knowledge(follow_links=True)`.
- **`link_memories(source, target, link_type)`** — connects two facts the agent already knows;
  `supports` / `contradicts` keep both current.
- **`search_knowledge(follow_links=True)`** — adds one hop of linked context to every hit.
- **The scanner graph** — `run_scan` links column and relationship facts to their table facts with
  `supports`. Searching `FINANCE.TRANSACTIONS` with `follow_links=True` returns the table fact plus
  its columns, without a join.

The right-side Memory Context pane renders relations as `→ relation` / `← relation` chips under each
memory, with retired ones struck through.

## Key Takeaways — Part 2

- **Don't hand-roll the memory schema.** OAMP gives you `memory`, `thread`, and `context_card`. Skipping it costs weeks of bookkeeping code that has nothing to do with the agent's actual job.
- **Catalog views are training data.** `ALL_TABLES + ALL_TAB_COLUMNS + ALL_CONSTRAINTS + V$SQL` mined into prose facts is how you teach an agent your schema without fine-tuning a model.
- **`body_hash` makes re-scans free.** The scanner only re-embeds facts whose underlying text changed. Hourly re-scans become viable when the dedup is content-based, not time-based.
- **Procedural memory is different.** `scan_history` (when/how the agent ran) is queried by time and owner, not by meaning — keep it as a regular indexed table, not an OAMP memory.
- **Links beat duplication.** Relation types carry lifecycle semantics: `supersedes`/`refines`/`duplicates` retire the target, `contradicts`/`supports` keep both. Retired facts disappear from normal search but stay one hop away, so corrections never lose history.

## Troubleshooting

**`ValueError: user already exists`** — OAMP's `add_user` and `add_agent` reject duplicate IDs. The pre-built `memory_client` initialisation in §2.2 wraps these calls in `try/except ValueError`, but if you call them yourself, do the same.

**`ORA-00942: table or view does not exist`** — `ALL_TABLES` etc. are catalog views every user can read. If you see this, you're probably querying as a user without `SELECT_CATALOG_ROLE` (the setup cell granted it).

**Scanner returns 0 facts** — Check the `owner` argument is the schema name in uppercase. `ALL_TABLES.owner` is always uppercase even if you `CREATE USER demo`.
