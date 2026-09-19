# Workshop TODO checklist

The canonical workshop is the nine-TODO path in `notebook_student.ipynb`. Each checkpoint is an assertion in the notebook: most sit in the cell right after their TODO, and a few run later in the same section so the data they need (registered tools, seeded skills) exists first. A failure identifies the unfinished block before later work depends on it.

- [ ] **TODO 1 — ask the bare model** in Part 1. Set `QUESTION` and run the chat client with no memory, retrieval, or tools.
- [ ] **TODO 2 — `OracleONNXEmbedder.embed`** in Part 2. Embed text with the in-database ONNX model, one `VECTOR_EMBEDDING` SELECT per text.
- [ ] **TODO 3 — `_scan_tables`** in Part 2. Read Oracle catalog metadata and emit `Fact` objects describing the Meridian Bank `FINANCE` tables.
- [ ] **TODO 4 — `retrieve_knowledge`** in Part 3. Oversample OAMP memories, filter them, and rerank the useful candidates.
- [ ] **TODO 5 — `hybrid_rrf_search_memories`** in Part 3. Fuse vector and Oracle Text ranks with Reciprocal Rank Fusion in one SQL statement.
- [ ] **TODO 6 — `retrieve_tools`** in Part 6. Rank the `toolbox` by cosine distance to the query, rerank the shortlist, and merge the always-on tools.
- [ ] **TODO 7 — `tool_run_sql`** in Part 6. Register a safe, read-only `SELECT`/`WITH` tool and return bounded JSON results.
- [ ] **TODO 8 — `tool_list_skills`** in Part 6. Search the `skillbox` semantically and return top-k skills as JSON.
- [ ] **TODO 9 — `agent_turn`** in Part 7. Assemble context, call the model, dispatch tools, enforce iteration/time limits, and produce a final answer.

There is no tenth TODO for identity. The rule set is installed for you by `app/scripts/setup_deep_security.py`, and the reference notebook's **Part 8** walks through what it enforces — see [Part 8](part-8-deep-data-security.md).

## Before you start

- [ ] Codespace or local Oracle is reachable.
- [ ] `ALL_MINILM_L12_V2` is available in the database (and `RERANKER_ONNX` if the cross-encoder step is provisioned).
- [ ] The `FINANCE` schema is seeded (see `app/scripts/seed.py`).
- [ ] The identity rules are installed (see `app/scripts/setup_deep_security.py`); the Codespace runs this for you during setup.
- [ ] The notebook kernel has the dependencies from `requirements.txt`.
- [ ] `notebook_student.ipynb` opens from the repository root.

## After the nine TODOs

- [ ] Run the three-turn notebook demo on one thread (discovery → live SQL → correction).
- [ ] Open the running app at `http://localhost:3000`.
- [ ] Ask *"Which branch regions have the most FLAGGED or BLOCKED transactions?"*
- [ ] Switch the header persona to **Analyst — Europe & Middle East** and re-ask; watch the rows change.
- [ ] Open the memory pane and confirm the correction from turn 3 is there.
- [ ] Switch the header persona to **Compliance Officer** and ask for Suspicious Activity Reports: **15** rows. Switch to **Analyst (default)** and ask the same thing: **0** rows. Nothing in the UI changed — the database answered differently.

## Advanced reference material

Parts 4 (DBFS scratchpad), 5 (Oracle MLE), 8 (identity-aware data access), 9 (JSON Relational Duality Views), and 11 (tool-output offload) are **not** required TODOs in the 90-minute path. They remain as guides, and their code is live in the app and in the reference notebooks:

- [Part 8 — Identity-aware data access](part-8-deep-data-security.md) — why the same SQL returns different rows per persona, what Oracle Deep Data Security does on Enterprise-class 26ai, and what the `DBMS_RLS` fallback can and cannot guarantee.

- [`notebook_complete_with_setup_code.ipynb`](../notebook_complete_with_setup_code.ipynb) — full source including every Oracle DDL statement.
- [`enterprise_data_agent.ipynb`](../enterprise_data_agent.ipynb) — the original end-to-end source notebook.

Use them when you want to deploy this harness against an Oracle that isn't the workshop Codespace, or when you want the deeper chapters.
