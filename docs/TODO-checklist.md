# Workshop TODO checklist

The canonical workshop is the five-TODO path in `notebook_student.ipynb`. Each checkpoint is an assertion in the next notebook cell, so a failure identifies the unfinished block before later work depends on it.

- [ ] **TODO 1 — `_scan_tables`** in Part 2. Read Oracle catalog metadata and emit `Fact` objects describing the Meridian Bank `FINANCE` tables.
- [ ] **TODO 2 — `retrieve_knowledge`** in Part 3. Oversample OAMP memories, filter them, and rerank the useful candidates.
- [ ] **TODO 3 — `hybrid_rrf_search_memories`** in Part 3. Fuse vector and Oracle Text ranks with Reciprocal Rank Fusion in one SQL statement.
- [ ] **TODO 4 — `tool_run_sql`** in Part 6. Register a safe, read-only `SELECT`/`WITH` tool and return bounded JSON results.
- [ ] **TODO 5 — `agent_turn`** in Part 7. Assemble context, call the model, dispatch tools, enforce iteration/time limits, and produce a final answer.

## Before you start

- [ ] Codespace or local Oracle is reachable.
- [ ] `ALL_MINILM_L12_V2` is available in the database (and `RERANKER_ONNX` if the cross-encoder step is provisioned).
- [ ] The `FINANCE` schema is seeded (see `app/scripts/seed.py`).
- [ ] The notebook kernel has the dependencies from `requirements.txt`.
- [ ] `notebook_student.ipynb` opens from the repository root.

## After the five TODOs

- [ ] Run the three-turn notebook demo on one thread (discovery → live SQL → correction).
- [ ] Open the running app at `http://localhost:3000`.
- [ ] Ask *"Which branch regions have the most FLAGGED or BLOCKED transactions?"*
- [ ] Switch the header persona to **Analyst — Europe & Middle East** and re-ask; watch the rows change.
- [ ] Open the memory pane and confirm the correction from turn 3 is there.

## Advanced reference material

Parts 4 (DBFS scratchpad), 5 (Oracle MLE), 9 (JSON Relational Duality Views), and 11 (tool-output offload) are **not** required TODOs in the 90-minute path. They remain as guides, and their code is live in the app and in the reference notebooks:

- [`notebook_complete_with_setup_code.ipynb`](notebook_complete_with_setup_code.ipynb) — full source including every Oracle DDL statement.
- [`enterprise_data_agent.ipynb`](enterprise_data_agent.ipynb) — the original end-to-end source notebook.

Use them when you want to deploy this harness against an Oracle that isn't the workshop Codespace, or when you want the deeper chapters.
