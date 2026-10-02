#!/usr/bin/env python3
"""Insert the four "without vs with" concept demos into the lightweight pair.

The 90-minute workshop is concept-driven: each Part teaches a primitive. These
cells let students *see* the primitive working by contrasting the naive baseline
against what they just built:

  * after §2.2 — OAMP vs a hand-rolled Python dict
  * after §3.4 — no similarity search vs `retrieve_knowledge` (TODO 4)
  * after §7.1 — no context summarization vs OAMP's context card
  * after §7.3 — no DBFS vs Oracle DBFS (ACID scratch state; guide: Part 4)

They add NO TODO stubs and NO checkpoints — the exercise count is unchanged.
The insertion is idempotent: every cell carries a `workshop:concept-demo:<key>`
marker and the script skips any demo already present.

Run from the repository root:

    python scripts/add_concept_demos.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = {
    "student": ROOT / "notebook_student.ipynb",
    "complete": ROOT / "notebook_complete.ipynb",
}

# Insertion indices (insert *before* this cell). Both notebooks have the same
# cell layout up to the Part 12 block, so the anchors are shared.
ANCHORS = {
    "student":  {"oamp": 31, "similarity": 52, "context": 74, "dbfs": 83},
    "complete": {"oamp": 31, "similarity": 52, "context": 74, "dbfs": 83},
}


OAMP_MD = """## Concept check — what OAMP replaces

`oracleagentmemory` is the whole memory layer — in-database vectors, threads, context cards, user/agent scoping, extraction, provenance — as tables you can query with SQL.

Below: the same fact kept in a Python dict and matched by keyword, then stored through OAMP and found by *meaning* on a rephrased question.

<!-- workshop:concept-demo:oamp -->"""

OAMP_CODE = '''# ============================================================================
# WITHOUT OAMP vs WITH OAMP — the memory layer you would otherwise build yourself
# ============================================================================
q = "monetary denomination scale"   # deliberately shares NO words with the facts below

# ---- WITHOUT: an in-kernel dict, matched by keyword overlap ----------------
naive_memory = [
    {"subject": "FINANCE.TRANSACTIONS.amount_cents",
     "body": "Transaction amounts are stored in USD cents, never dollars."},
    {"subject": "FINANCE.CUSTOMERS.risk_rating",
     "body": "Customer risk rating is a 1-100 score; higher means riskier."},
]

def naive_search(query):
    q_words = set(query.lower().split())
    ranked = []
    for row in naive_memory:
        overlap = len(q_words & set((row["subject"] + " " + row["body"]).lower().split()))
        if overlap:
            ranked.append((overlap, row["subject"]))
    return [s for _, s in sorted(ranked, reverse=True)]

print("WITHOUT OAMP — a Python dict, matched by keyword overlap:")
print("   query:", repr(q))
print("   hits :", naive_search(q) or "[]  <- zero token overlap, so it finds nothing")
print("   -> no meaning, no persistence, no user/agent scoping, no provenance.")

# ---- WITH: OAMP, embedded and searchable by meaning ------------------------
memory_client.add_memory(
    "Table FINANCE.TRANSACTIONS column AMOUNT_CENTS: amounts are stored in USD CENTS, never dollars.",
    user_id=USER_ID, agent_id=AGENT_ID,
    metadata={"kind": "column", "subject": "FINANCE.TRANSACTIONS.AMOUNT_CENTS"},
)
hits = memory_client.search(q, user_id=USER_ID, agent_id=AGENT_ID,
                            record_types=["memory"], max_results=3)
print("\\nWITH OAMP — the same query, searched by meaning:")
for h in hits:
    d = getattr(h, "distance", None)
    subject = (h.metadata or {}).get("subject", "?")
    print(f"   distance={float(d):.4f}  {subject}" if d is not None else f"   {subject}")
print("   -> the fact is retrieved despite zero shared keywords, stored in the EDA_ONNX_* tables,")
print("      scoped to user/agent, and reusable from any later turn or process.")
'''


SIM_MD = """## Concept check — retrieval without vectors

A substring (`LIKE`) lookup cannot answer a question that shares no words with the stored fact. Below: the naive baseline, then `retrieve_knowledge()` from **TODO 4** — same question, one of them finds `FINANCE.TRANSACTIONS.AMOUNT_CENTS`.

<!-- workshop:concept-demo:similarity -->"""

SIM_CODE = '''# ============================================================================
# WITHOUT similarity search vs WITH it — the function from TODO 4
# ============================================================================
q = "how are transaction amounts stored — dollars or cents?"

# ---- WITHOUT: a plain substring lookup over the stored memory bodies -------
print("WITHOUT vector search — LIKE over the memory body:")
with agent_conn.cursor() as cur:
    cur.execute(
        f"SELECT COUNT(*) FROM {MEMORY_TABLE} "
        f" WHERE LOWER(DBMS_LOB.SUBSTR(content, 4000, 1)) LIKE '%' || LOWER(:q) || '%'",
        q="transaction amounts stored dollars cents",
    )
    print("   rows matching that exact phrase:", cur.fetchone()[0])
print("   -> ~0 rows. The fact is stored as 'amounts are stored in USD CENTS'; a natural")
print("      question shares no long substring with it. Lexical search only wins on tokens.")

# ---- WITH: the similarity search you implemented (TODO 4) -----------------
print("\\nWITH similarity search — retrieve_knowledge() (vector + rerank):")
for h in retrieve_knowledge(q, k=3):
    d = h.get("distance")
    tag = f"distance={float(d):.4f}  " if d is not None else ""
    print(f"   {tag}{h['subject']}")
print("   -> the right fact surfaces with zero shared words, because the match is semantic.")
'''


CTX_MD = """## Concept check — context summarization

`build_context()` is half the story: OAMP also keeps a **rolling context card** per thread (`enable_context_summary=True`, refreshed every `context_summary_update_frequency` turns), so a long thread does not replay its raw transcript every turn. Below: four corrections on a throwaway thread, raw transcript vs generated card — then the card's sections, and the two ways the harness can call it.

<!-- workshop:concept-demo:context -->"""

CTX_CODE = '''# ============================================================================
# WITHOUT context summarization vs WITH it — OAMP's context card
# ============================================================================
from oracleagentmemory.apis.thread import Message

probe_thread = "context-demo"
_corrections = [
    "Remember: transactions.amount_cents is USD CENTS, never dollars.",
    "Also: customers.risk_rating is a 1-100 score, higher means riskier.",
    "Third: branches.region is one of AMERICAS, EUROPE, MIDDLE_EAST, ASIA_PACIFIC.",
    "Fourth: SAR_REPORTS is compliance-only and forbidden to analysts.",
]
get_thread(probe_thread).add_messages([Message(role="user", content=m) for m in _corrections])

_raw = "\\n".join(m.content for m in get_thread(probe_thread).get_messages())
try:
    _card = str(get_thread(probe_thread).get_context_card() or "")
except Exception as e:
    _card = ""
    print("  ! OAMP context card unavailable:", type(e).__name__)

print("WITHOUT the context card, every turn replays the raw transcript:")
print(f"   raw transcript: {len(_raw)} chars across {len(_corrections)} messages")
print("   -> unbounded growth; older corrections eventually fall outside the window.")

print("\\nWITH OAMP's context card (enable_context_summary=True, refreshed every 4 turns):")
print(f"   card: {len(_card)} chars — a structured, bounded summary")
if _card:
    print("   preview:", _card[:280].replace(chr(10), " "))
if _card and _raw:
    print(f"   right now raw:card = {len(_raw) / max(len(_card), 1):.2f}x — with only "
          f"{len(_corrections)} messages the card is larger;")
    print("   append 100 turns and the transcript grows linearly while the card stays ~constant.")
print("\\n-> The card is a rolling, model-generated summary of topics + decisions. It is what")
print("   lets a long thread stay inside the context window without losing what was decided.")

# --- what is inside it, and the two ways to call it --------------------------
_sections = [tag for tag in ("topics", "summary", "relevant_information", "recent_messages")
             if f"<{tag}>" in _card]
print(f"\\nThe card is a structured block — {' · '.join(_sections)} — not a transcript,")
print("   and the harness chooses its shape with two arguments:")

_self_contained = str(get_thread(probe_thread).get_context_card(max_recent_messages=2) or "")
_raw_tail = str(get_thread(probe_thread).get_context_card(except_last_messages=2,
                                                          max_recent_messages=0) or "")
print(f"   get_context_card(max_recent_messages=2)                    -> {len(_self_contained):>5} chars, "
      f"recent messages inside: {'<recent_messages>' in _self_contained}")
print(f"   get_context_card(except_last_messages=2, max_recent_...=0) -> {len(_raw_tail):>5} chars, "
      f"recent messages inside: {'<recent_messages>' in _raw_tail}")
print("   The first is self-contained: send the card alone. The second leaves the last two")
print("   turns out — you send those raw, so they are never summarised twice (prompt-cache friendly).")
print("   §7.1's build_context() calls exactly this and prepends the card to the prompt.")
'''


DBFS_MD = """## Concept check — DBFS scratch state

Mid-task scratch space is a real problem: a Python variable is not transactional, invisible to other sessions, and gone on restart. Below: a draft in a Python variable, then the same bytes written to **Oracle DBFS** — a filesystem inside the database — and read back through a second connection. Guide: [Part 4](docs/part-4-dbfs.md).

<!-- workshop:concept-demo:dbfs -->"""

DBFS_CODE = '''# ============================================================================
# WITHOUT DBFS vs WITH DBFS — durable, transactional scratch state
# ============================================================================
draft = ("SELECT region, COUNT(*) FROM FINANCE.transactions "
         "WHERE status = 'FLAGGED' GROUP BY region")

# ---- WITHOUT: a Python variable -------------------------------------------
print("WITHOUT DBFS — a Python variable holds the draft:")
print("   ", draft[:70], "...")
agent_conn.rollback()   # a DB rollback cannot touch a Python variable
print("   after agent_conn.rollback(): the draft is still here (it was never in the DB).")
print("   -> not transactional with the agent's writes, invisible to any other session,")
print("      gone the moment the kernel restarts.")

# ---- WITH: Oracle DBFS — a filesystem INSIDE the database -----------------
DBFS_MOUNT = "/scratch"
DBFS_DIR   = f"{DBFS_MOUNT}/workshop"
DBFS_PATH  = f"{DBFS_DIR}/amount_rule.sql"

_MKDIR = ("DECLARE l_props DBMS_DBFS_CONTENT_PROPERTIES_T := DBMS_DBFS_CONTENT_PROPERTIES_T(); "
          "BEGIN DBMS_DBFS_CONTENT.CREATEDIRECTORY(path => :d, properties => l_props); "
          "EXCEPTION WHEN OTHERS THEN NULL; END;")
_DELETE = "BEGIN DBMS_DBFS_CONTENT.DELETEFILE(:p); EXCEPTION WHEN OTHERS THEN NULL; END;"
_CREATE = ("DECLARE l_props DBMS_DBFS_CONTENT_PROPERTIES_T := DBMS_DBFS_CONTENT_PROPERTIES_T(); "
           "l_blob BLOB := :b; BEGIN "
           "DBMS_DBFS_CONTENT.CREATEFILE(path => :p, properties => l_props, content => l_blob); "
           "COMMIT; END;")

with agent_conn.cursor() as cur:
    cur.execute(_MKDIR, d=DBFS_DIR)
    cur.execute(_DELETE, p=DBFS_PATH)
    cur.setinputsizes(b=oracledb.DB_TYPE_BLOB)
    cur.execute(_CREATE, p=DBFS_PATH, b=draft.encode())
agent_conn.commit()
print(f"\\nWITH DBFS — wrote {len(draft)} bytes to {DBFS_PATH}")

# Prove it is really IN the database: read the bytes back through a BRAND-NEW
# connection (not agent_conn).
agent_conn2 = connect(AGENT_USER, AGENT_PASS, SYS_DSN)
_READ = ("DECLARE l_props DBMS_DBFS_CONTENT_PROPERTIES_T := DBMS_DBFS_CONTENT_PROPERTIES_T(); "
         "l_blob BLOB; l_item NUMBER; BEGIN "
         "DBMS_DBFS_CONTENT.GETPATH(path => :p, properties => l_props, content => l_blob, item_type => l_item); "
         ":out := l_blob; END;")
with agent_conn2.cursor() as cur:
    out = cur.var(oracledb.DB_TYPE_BLOB)
    cur.execute(_READ, p=DBFS_PATH, out=out)
    read_back = out.getvalue().read().decode()
print("   read back from a fresh connection:", read_back[:60], "...")
assert read_back == draft, "DBFS round-trip mismatch"
print("   OK — identical bytes: the draft is committed in the database, not in kernel RAM.")
print("\\n-> DBFS gives the agent a real, transactional filesystem: the same ACID guarantees")
print("   as the memory tables, visible across sessions, surviving a kernel restart.")
agent_conn2.close()
'''


DEMOS = {
    "oamp":       (OAMP_MD, OAMP_CODE),
    "similarity": (SIM_MD, SIM_CODE),
    "context":    (CTX_MD, CTX_CODE),
    "dbfs":       (DBFS_MD, DBFS_CODE),
}


def _cell(cell_type: str, source: str) -> dict:
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _already_present(notebook: dict, key: str) -> bool:
    marker = f"workshop:concept-demo:{key}"
    return any(marker in "".join(c.get("source", [])) for c in notebook["cells"])


def insert(notebook: dict, anchors: dict[str, int]) -> list[str]:
    added = []
    # Descending so earlier anchor indices stay valid as we insert.
    for key in sorted(anchors, key=lambda k: anchors[k], reverse=True):
        if _already_present(notebook, key):
            continue
        md, code = DEMOS[key]
        at = anchors[key]
        notebook["cells"].insert(at, _cell("markdown", md))
        notebook["cells"].insert(at + 1, _cell("code", code))
        added.append(key)
    return added


def main() -> int:
    for name, path in NOTEBOOKS.items():
        notebook = json.loads(path.read_text(encoding="utf-8"))
        before = len(notebook["cells"])
        added = insert(notebook, ANCHORS[name])
        path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{path.name}: {before} -> {len(notebook['cells'])} cells "
              f"(added: {', '.join(added) if added else 'nothing — already present'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
