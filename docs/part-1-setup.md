# Part 1: Setup & connectivity

## What you are building

An **AML / financial-crime data agent** for Meridian Bank: a small loop on top of Oracle AI Database 26ai that lets an investigator ask natural-language questions of live transaction data without learning the schema.

The formula:

```text
Agent = Model + Harness
```

The model emits tokens. Everything else — state, memory, tool dispatch, identity, budgets, retry logic — is **harness code**. Most "agent quality" complaints are harness problems, not model problems. Part 1 connects the notebook to Oracle; the later parts implement the five core harness blocks.

## Canonical environment

The workshop uses **two** database users, and the split is the trust boundary:

| Oracle user | Owns | Used by |
|---|---|---|
| `SYS` | the entire database (super-user) | one-time bootstrap only |
| `AGENT` | harness state — OAMP memory tables, `toolbox`, `skillbox`, the DBFS scratchpad | every notebook cell |
| `FINANCE` | Meridian Bank business data — `branches`, `customers`, `accounts`, `cards`, `merchants`, `transactions`, `loans`, `sar_reports`, plus `account_dv` / `customer_dv` | the agent, via read-only `run_sql` |

`AGENT` is granted `SELECT` on `FINANCE`; it cannot write there. If a hostile prompt got the agent to issue `DROP TABLE`, it could only drop something `AGENT` owns.

In Codespaces, `.devcontainer/setup_runtime.sh` boots Oracle and runs the three provisioning scripts in order:

| Script | What it provisions |
|---|---|
| [`app/scripts/bootstrap.py`](app/scripts/bootstrap.py) | `AGENT` user, `vector_memory_size` / `pga_aggregate_limit`, the in-DB ONNX embedder, DBFS |
| [`app/scripts/seed.py`](app/scripts/seed.py) | the `FINANCE` schema, the AML seed data, the duality views, the skillbox |
| [`app/scripts/setup_advanced.py`](app/scripts/setup_advanced.py) | the Oracle Text index and the identity policies |

`.devcontainer/start_app.sh` then starts the Flask backend on port 8000 and the React UI on port 3000. Everything is idempotent and safe to re-run.

| Setting | Default |
|---|---|
| Database DSN | `localhost:1521/FREEPDB1` |
| SYS password | `OraclePwd_2025` |
| Agent user / password | `AGENT` / `AgentPwd_2025` |
| Demo user / password | `FINANCE` / `FinancePwd_2025` |
| Required embedder | `ALL_MINILM_L12_V2` (384 dimensions) |
| Reranker | `RERANKER_ONNX` |
| Running app | `http://localhost:3000` |

## Models and the network boundary

`ALL_MINILM_L12_V2` is loaded *inside* Oracle and called with `VECTOR_EMBEDDING(...)`, so embedding and retrieval never call a hosted vector service. `RERANKER_ONNX` is called through `PREDICTION(...)`. Both live where the data lives: same backups, same audit, same security model.

The chat model is selected with `LLM_PROVIDER`:

- `oci` (the workshop default) uses `OCI_GENAI_API_KEY` against OCI GenAI's OpenAI-compatible endpoint. This is the only outbound network call in the whole harness.
- `openai` uses `OPENAI_API_KEY` instead.

The app normalizes a bare OCI regional endpoint by appending `/openai/v1`; the notebook does the same when it initializes its client.

## The two database parameters that matter

**`vector_memory_size`** — Oracle 26ai keeps HNSW vector indexes in a dedicated in-memory pool. On a stock Free image it ships at `0`, so any `CREATE VECTOR INDEX ... ORGANIZATION INMEMORY NEIGHBOR GRAPH` raises `ORA-51962` and your retrieval silently degrades to full-table cosine scans. The bootstrap allocates 512 MiB at SPFILE scope; the first time it does so Oracle needs a restart, which the devcontainer handles.

**`pga_aggregate_limit`** — the cross-encoder reranker allocates enough transient PGA per call that the Free build's default ceiling (~2 GiB) is exceeded under modest load, surfacing as `ORA-04036`. The bootstrap raises it to 4 GiB at the CDB level.

You don't need to remember the details — both are configured for you. They're explained here so you know what to look up if you hit these errors against a non-Codespaces database.

## There is no TODO in Part 1

The Codespace already ran the provisioning scripts, so `AGENT`, the `FINANCE` schema, the vector pool, the ONNX models, the duality views, and the identity policies are all in place. The notebook just opens a session:

```python
SYS_DSN    = "localhost:1521/FREEPDB1"
AGENT_USER = "AGENT"
AGENT_PASS = "AgentPwd_2025"
DEMO_USER  = "FINANCE"

agent_conn = connect(AGENT_USER, AGENT_PASS, SYS_DSN)
```

The `connect` helper retries because a Docker healthcheck can pass before Oracle's listener is ready to accept application sessions. After the connection succeeds, Part 2 creates the OAMP client and starts scanning `FINANCE` catalog metadata.

If you want to see *how* Oracle was provisioned, read `app/scripts/bootstrap.py`, `seed.py`, and `setup_advanced.py`, or open [`notebook_complete_with_setup_code.ipynb`](notebook_complete_with_setup_code.ipynb) — the full source that includes every DDL statement.

## Verify the running app

In another terminal:

```bash
curl http://localhost:8000/api/health
```

Then open the UI and confirm the header shows the **Analyst (default)** persona:

<http://localhost:3000>

If the app is not serving:

```bash
bash .devcontainer/start_app.sh
tail -60 .devcontainer/logs/backend.log
tail -40 .devcontainer/logs/frontend.log
```

## Key takeaways — Part 1

- **Agent = Model + Harness.** The model emits tokens; everything else (state, dispatch, memory, identity, budgets) is harness code.
- **Separate the agent's DB user from the data's DB user.** `AGENT` owns harness state; `FINANCE` owns the bank data. The trust boundary is grants, not Python code — and it makes the persona demo in the app real.
- **`vector_memory_size` is non-optional for HNSW.** Without it, vector-index creation raises `ORA-51962`.
- **ONNX models load *into* the database.** Embeddings come from `VECTOR_EMBEDDING(...)` SQL calls, not network round-trips.
- **The AML use case already has opinions in the data.** `transactions.amount_cents` is USD **cents** and `customers.risk_rating` is a 1–100 score — both documented with `COMMENT ON COLUMN` so the scanner (Part 2) teaches the model those rules.

## Troubleshooting

**`ORA-12541: TNS:no listener`** — the Oracle container isn't ready yet. Wait 30 seconds and retry.

**`ORA-01017: invalid username/password`** — `AGENT` or `FINANCE` wasn't created; re-run `bash .devcontainer/setup_runtime.sh`.

**`ORA-51962: vector memory area is out of space`** — `vector_memory_size = 0`. Re-run `app/scripts/bootstrap.py`, restart Oracle, then restart the kernel.

See the [troubleshooting guide](troubleshooting.md) for more.
