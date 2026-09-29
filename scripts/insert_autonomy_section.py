"""Insert the Codespaces orientation cells and the Part 12 (autonomous AML
triage) section into the workshop notebooks.

Idempotent: every block is bracketed by `<!-- workshop:<name>:begin -->` /
`<!-- workshop:<name>:end -->` sentinels, so re-running replaces the block
instead of stacking copies. Edit the constants below — never hand-edit the
generated cells — then run from the repository root:

    python scripts/insert_autonomy_section.py

Targets:

    notebook_student.ipynb     preflight + Part 12 (+ the kernel-check cell)
    notebook_complete.ipynb    the same blocks, in the answer key

Notebook outputs are preserved: the generator only ever rewrites the cells
inside its sentinels, so an executed notebook stays executed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STUDENT = ROOT / "notebook_student.ipynb"
COMPLETE = ROOT / "notebook_complete.ipynb"

BEGIN = "<!-- workshop:{name}:begin -->"
END = "<!-- workshop:{name}:end -->"

CLOSE_ANCHOR = "# Closing thoughts — and the running app"
CONNECT_ANCHOR = "agent_conn = connect(AGENT_USER, AGENT_PASS, SYS_DSN)"


# --------------------------------------------------------------------------
# Cell helpers
# --------------------------------------------------------------------------
def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": text.splitlines(keepends=True)}


def block(name: str, cells: list[dict]) -> list[dict]:
    """Bracket a block of cells with the sentinels used for idempotent replacement."""
    return [md(BEGIN.format(name=name))] + cells + [md(END.format(name=name))]


def find_cell(cells: list[dict], needle: str) -> int:
    hits = [i for i, cell in enumerate(cells) if needle in "".join(cell["source"])]
    if len(hits) != 1:
        raise SystemExit(f"anchor {needle!r} matched {len(hits)} cells (need exactly 1)")
    return hits[0]


def _without_block(cells: list[dict], name: str) -> tuple[list[dict], list[dict]]:
    """Return (cells outside the block, cells inside it)."""
    begin, end = BEGIN.format(name=name), END.format(name=name)
    kept, inner, dropping = [], [], False
    for cell in cells:
        source = "".join(cell["source"])
        if begin in source:
            dropping = True
            continue
        if dropping:
            if end in source:
                dropping = False
            else:
                inner.append(cell)
            continue
        kept.append(cell)
    if dropping:
        raise SystemExit(f"unterminated {name} block")
    return kept, inner


def merge_block(name: str, new_cells: list[dict], previous: list[dict]) -> list[dict]:
    """Wrap `new_cells` in the block's sentinels, keeping unchanged cells as they are.

    A cell whose source is identical to the one it replaces keeps its old cell
    object — and with it its outputs and execution count — so re-running this
    generator on an executed notebook does not throw away results. A cell whose
    source changed comes back unexecuted, which is the only honest state for it.
    """
    merged = []
    for index, cell in enumerate(new_cells):
        old = previous[index] if index < len(previous) else None
        if old is not None and old["cell_type"] == cell["cell_type"] and old["source"] == cell["source"]:
            merged.append(old)
        else:
            merged.append(cell)
    return block(name, merged)


def replace_text(cells: list[dict], needle: str, replacement: str) -> None:
    for cell in cells:
        source = "".join(cell["source"])
        if needle in source:
            cell["source"] = source.replace(needle, replacement, 1).splitlines(keepends=True)
            return
    raise SystemExit(f"text anchor not found: {needle[:60]!r}")


# --------------------------------------------------------------------------
# Self-check cell (the notebook's first runnable cell)
# --------------------------------------------------------------------------


SELF_CHECK_MD = """## 0.1 Run this first — kernel check

Confirms the notebook kernel has the workshop dependencies and prints the URL of the running app. If it fails with `ModuleNotFoundError: No module named 'oracledb'`, the kernel is wrong: Command Palette → **Notebook: Select Notebook Kernel** → **Python 3.11** (`/usr/local/bin/python`)."""


SELF_CHECK = '''# §0.1 — Run me first: kernel check + where the running app lives.
import importlib.util, os, platform, sys

_missing = [m for m in ("numpy", "oracledb", "openai", "oracleagentmemory")
            if importlib.util.find_spec(m) is None]
if _missing:
    raise RuntimeError(
        f"This kernel is missing: {', '.join(_missing)}.\\n"
        "Pick the workshop interpreter: Command Palette -> 'Notebook: Select Notebook Kernel' ->\\n"
        "Python 3.11 at /usr/local/bin/python (see images/select_kernel.png).\\n"
        "Everything is pre-installed for that interpreter — do not pip install."
    )

print(f"✅ kernel: Python {platform.python_version()} · {sys.executable}")
print(f"✅ working directory: {os.getcwd()}")

_codespace = os.environ.get("CODESPACE_NAME", "").strip()
_domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip()
print("\\nRunning app — same Oracle, same memory store this notebook writes to:")
if _codespace and _domain:
    print(f"  forwarded: https://{_codespace}-3000.{_domain}   "
          f"(API health: https://{_codespace}-8000.{_domain}/api/health)")
print("  localhost: http://localhost:3000   (API health: http://localhost:8000/api/health)")
print("  If the preview did not open, use the PORTS tab.")'''


# --------------------------------------------------------------------------
# Preflight block — inserted right after the AGENT connection cell
# --------------------------------------------------------------------------
PREFLIGHT_MD = """## 1.3 Preflight — is this Codespace ready?

Twelve checks in one table: the `FINANCE` seed, the ONNX embedder and reranker, the Oracle Text index, `toolbox` / `skillbox`, the API keys. Every ❌ prints the command that fixes it; the two checks the rest of the notebook cannot survive raise instead of warning."""


PREFLIGHT_CODE = '''# §1.3 — Preflight. Reads the same catalogs the agent will scan, and the same env the
# harness reads. Nothing is written; run it as often as you like.
from importlib.metadata import version as _pkg_version


def _scalar(sql, default=None, **binds):
    """Single-value query; returns `default` if the object does not exist yet."""
    try:
        with agent_conn.cursor() as cur:
            cur.execute(sql, **binds)
            return cur.fetchone()[0]
    except oracledb.DatabaseError:
        return default


def _catalog(query, **binds):
    """Self-contained row fetch — the preflight runs before Part 12 defines `_rows`."""
    with agent_conn.cursor() as cur:
        cur.execute(query, **binds)
        return cur.fetchall()


def _check(label, ok, detail="", fix=""):
    print(f"  {'✅' if ok else '❌'} {label:<32} {detail}")
    if not ok and fix:
        print(f"     ↳ fix: {fix}")
    return ok


print("Environment")
print(f"  ✅ {'python':<32} {sys.version.split()[0]} at {sys.executable}")
for _pkg in ("oracledb", "oracleagentmemory", "openai", "numpy"):
    try:
        print(f"  ✅ {_pkg:<32} {_pkg_version(_pkg)}")
    except Exception:
        print(f"  ⚠️  {_pkg:<32} version unknown")

print("\\nOracle — AGENT schema (the harness's own state)")
_mem_table = _scalar("SELECT COUNT(*) FROM user_tables WHERE table_name = 'EDA_ONNX_MEMORY'", 0)
_mem_rows = _scalar("SELECT COUNT(*) FROM eda_onnx_memory", 0) if _mem_table else 0
print(f"  ✅ {'OAMP memory table':<32} EDA_ONNX_MEMORY · {_mem_rows} memor{'y' if _mem_rows == 1 else 'ies'}")
_text_idx = _scalar("SELECT COUNT(*) FROM user_indexes WHERE index_name = 'EDA_MEMORY_TEXT_IDX'", 0)
print(f"  {'✅' if _text_idx else '⚠️ '} {'Oracle Text index':<32} "
      f"{'EDA_MEMORY_TEXT_IDX present' if _text_idx else 'absent — §3.3a creates it (keyword leg needs it)'}")
_toolbox = _scalar("SELECT COUNT(*) FROM toolbox", None)
_skillbox = _scalar("SELECT COUNT(*) FROM skillbox", None)
print(f"  {'✅' if _toolbox is not None else '⚠️ '} {'toolbox / skillbox':<32} "
      f"{_toolbox if _toolbox is not None else 'missing'} tools · "
      f"{_skillbox if _skillbox is not None else 'missing'} skills")

print("\\nOracle — FINANCE (the bank's data; the agent only ever reads it)")
FINTECH_TABLES = ("BRANCHES", "CUSTOMERS", "ACCOUNTS", "CARDS", "MERCHANTS",
                  "TRANSACTIONS", "LOANS", "SAR_REPORTS", "SANCTIONS_SCREENINGS",
                  "BENEFICIAL_OWNERS", "WIRE_MESSAGES", "LOGIN_EVENTS",
                  "KYC_DOCUMENTS", "CASE_NOTES", "FX_RATES")
_present = {row[0] for row in _catalog(
    "SELECT table_name FROM all_tables WHERE owner = 'FINANCE'") if "$" not in row[0]}
_missing = [t for t in FINTECH_TABLES if t not in _present]
_txns = _scalar("SELECT COUNT(*) FROM finance.transactions", 0)
_flagged = _scalar("SELECT COUNT(*) FROM finance.transactions "
                   "WHERE status IN ('FLAGGED','BLOCKED') AND flag_reason IS NOT NULL", 0)
_sars = _scalar("SELECT COUNT(*) FROM finance.sar_reports", 0)
_seed_fix = "cd app && python scripts/bootstrap.py && python scripts/seed.py"
_check("FINANCE business tables", not _missing,
       f"{len(FINTECH_TABLES) - len(_missing)}/{len(FINTECH_TABLES)} present (Spatial index tables ignored)",
       fix=f"missing {', '.join(_missing)} — " + _seed_fix if _missing else "")
_alert_queue = _scalar(
    "SELECT COUNT(*) FROM (SELECT a.customer_id, t.flag_reason "
    "  FROM finance.transactions t JOIN finance.accounts a ON a.account_id = t.account_id "
    " WHERE t.status IN ('FLAGGED','BLOCKED') "
    "   AND t.txn_ts >= SYSTIMESTAMP - INTERVAL '30' DAY "
    " GROUP BY a.customer_id, t.flag_reason)", 0)
_check("transactions", _txns > 5000,
       f"{_txns} rows (Meridian Bank seed ≈ 23,600), {_flagged} flagged/blocked", fix=_seed_fix)
_check("AML alerts in the seed", _flagged > 0,
       f"{_alert_queue} alerts in the 30-day window (Part 12's queue)", fix=_seed_fix)
_check("SAR reports", _sars > 0, f"{_sars} reports (compliance-only table)", fix=_seed_fix)
_ops = {t: _scalar(f"SELECT COUNT(*) FROM finance.{t}", 0) for t in
        ("sanctions_screenings", "beneficial_owners", "wire_messages", "login_events",
         "kyc_documents", "case_notes", "fx_rates")}
_check("AML operational tables", all(v > 0 for v in _ops.values()),
       " · ".join(f"{k.replace('_', ' ')} {v}" for k, v in _ops.items()), fix=_seed_fix)

print("\\nIn-database models")
_embedder = _scalar("SELECT COUNT(*) FROM user_mining_models WHERE model_name = 'ALL_MINILM_L12_V2'", 0)
_reranker = _scalar("SELECT COUNT(*) FROM user_mining_models WHERE model_name = 'RERANKER_ONNX'", 0)
_check("ONNX embedder", bool(_embedder), "ALL_MINILM_L12_V2 (384-dim, in-database)",
       fix="cd app && python scripts/bootstrap.py")
print(f"  {'✅' if _reranker else '⚠️ '} {'ONNX reranker':<32} "
      f"{'RERANKER_ONNX present' if _reranker else 'absent — retrieval falls back to cosine ordering (fine)'}")

print("\\nChat LLM")
_keys = len(OCI_ROTATOR) if LLM_PROVIDER == "oci" and OCI_ROTATOR else 0
if LLM_PROVIDER == "openai":
    _keys = 1 if os.environ.get("OPENAI_API_KEY") else 0
print(f"  {'✅' if _keys else '❌'} {'credentials':<32} provider {LLM_PROVIDER} · model {os.environ['LLM_MODEL']} · {_keys} key(s)")
if LLM_PROVIDER == "oci":
    print(f"     endpoint: {OCI_ENDPOINT}")
if not _keys:
    print("     ↳ fix: add OCI_GENAI_API_KEY as a Codespaces secret (then restart), or")
    print("            echo 'OCI_GENAI_API_KEY=...' >> app/.env  — TODO 1 is the first live call.")

# The two hard requirements: without these, Blocks 2–12 cannot run.
if _missing or not _txns:
    raise RuntimeError("FINANCE is not seeded. Fix: " + _seed_fix)
if not _embedder:
    raise RuntimeError("The in-database embedder is missing. Fix: cd app && python scripts/bootstrap.py")

print("\\n✅ Preflight passed — every block below has what it needs.")'''


# --------------------------------------------------------------------------
# Part 12 — the autonomous AML triage capstone
# --------------------------------------------------------------------------
P12_INTRO_MD = """# Part 12 — The bank's morning: an autonomous AML triage

> 📖 Guide: [`docs/part-12-autonomous-aml-triage.md`](docs/part-12-autonomous-aml-triage.md) · ▶️ **no TODO — run it.** ~15 minutes, three alerts, each a full model round-trip.

Parts 1–7 built a harness that answers questions. A compliance desk does not work that way: alerts arrive on their own schedule and every one needs a decision the bank can defend. Autonomy here is four concrete properties:

| Property | Where it lives |
|---|---|
| **A trigger, not a prompt** | §12.3 builds the queue from `FINANCE` |
| **A decision with a stated reason** | §12.5–12.6 — a validated decision record |
| **A record a human can replay** | `AGENT.AML_TRIAGE` rows + `case_decision` memories |
| **A budget and a boundary** | metered model calls, ≤6 iterations / 120 s per alert, `ESCALATE` only recommends |

The agent cannot write to `FINANCE`, cannot file a SAR, and cannot see this queue at all without clearance ([Part 8](docs/part-8-deep-data-security.md)). The question §12.8 answers: if the desk ran every morning, what would it decide — and what would that be worth?"""


P12_GATE_CODE = '''# Part 12 uses the harness you built above. Fail here with one clear message instead of
# halfway through a triage run.
_PARTS_REQUIRED = ("agent_conn", "agent_turn", "chat", "retrieve_knowledge", "retrieve_tools",
                   "tool_run_sql", "write_facts", "Fact", "TOOLS")
_missing_symbols = [name for name in _PARTS_REQUIRED if name not in globals()]
assert not _missing_symbols, (
    f"❌ Part 12 needs {', '.join(_missing_symbols)} — finish the TODOs above "
    "(or open notebook_complete.ipynb) before running the capstone."
)
print("✅ harness present:", ", ".join(_PARTS_REQUIRED))'''


P12_DATA_MD = """## 12.1 What an alert is — the fraud data, in one screen

| Where | What it holds | Why the agent cares |
|---|---|---|
| `FINANCE.transactions.status` | `COMPLETED` / `FLAGGED` / `BLOCKED` | the bank's own rules already fired — this *is* the queue |
| `FINANCE.transactions.flag_reason` | which AML typology fired | turns a row into an investigation |
| `FINANCE.transactions.amount_cents` | integer USD **cents** | ÷100; the seed plants this trap deliberately |
| `FINANCE.sar_reports` | what compliance already filed | prior history changes today's decision |

| `flag_reason` | Pattern the seed plants |
|---|---|
| `STRUCTURING` | deposits just under the $10,000 CTR threshold, repeated |
| `GEO_VELOCITY` | one card, two far-apart regions, hours apart |
| `HIGH_RISK_COUNTRY` | wires to elevated-risk corridors after an inbound credit |
| `RAPID_CASH_OUT` | inbound wire, then ATM withdrawals within ~48 hours |
| `LARGE_CASH_DEPOSIT` | a single cash deposit above $50,000 |

A transaction is not an alert: *"this deposit was $9,983"* is noise, while *"nine deposits between $8,000 and $9,999 in two weeks, plus a SAR under review"* is a case. §12.3 builds that customer-scoped bundle in SQL."""


P12_LEDGER_MD = """## 12.2 The triage ledger — the harness's own bookkeeping

Each decision lands in two places, because two audiences read it:

| Store | Shape | Who reads it |
|---|---|---|
| `AGENT.AML_TRIAGE` | one row per `(customer, typology)`: decision, confidence, rationale, evidence window | an examiner or a SQL dashboard |
| OAMP memories, `kind="case_decision"` | the same decision as a sentence | **the agent itself**, next morning |

Note what is *not* happening: no writes to `FINANCE`, ever. The write surface is the `AGENT` schema — the trust boundary from Part 1, made literal."""


P12_LEDGER_CODE = '''# §12.2 — The ledger (created once) + two helpers the cells below share.
AML_LEDGER = "AGENT.AML_TRIAGE"


def _rows(sql, **binds):
    """Run SQL and return list[dict] with lowercased column names."""
    with agent_conn.cursor() as cur:
        cur.execute(sql, **binds)
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, row)) for row in cur]


def _money(cents):
    return f"${(cents or 0) / 100:,.2f}"


with agent_conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'AML_TRIAGE'")
    if not cur.fetchone()[0]:
        cur.execute("""
            CREATE TABLE aml_triage (
              customer_id    NUMBER(10),
              typology       VARCHAR2(60),
              customer_name  VARCHAR2(120),
              risk_rating    NUMBER(3),
              flagged_txns   NUMBER(6),
              exposure_cents NUMBER(15),
              window_start   TIMESTAMP,
              window_end     TIMESTAMP,
              decision       VARCHAR2(20),
              confidence     NUMBER(3,2),
              rationale      VARCHAR2(1000),
              next_action    VARCHAR2(400),
              sar_reason     VARCHAR2(60),
              decided_at     TIMESTAMP,
              decided_by     VARCHAR2(60),
              CONSTRAINT aml_triage_pk PRIMARY KEY (customer_id, typology)
            )""")
        print(f"created {AML_LEDGER}")
    else:
        print(f"{AML_LEDGER} already present")
agent_conn.commit()

_ledger_rows = _rows("SELECT COUNT(*) AS n FROM aml_triage")[0]["n"]
print(f"ledger: {_ledger_rows} decision(s) on record")
print("decision vocabulary: ESCALATE · KYC_REVIEW · DISMISS · REVIEW_REQUIRED — set by the harness, never by the model")'''


P12_QUEUE_MD = """## 12.3 The alert queue — a trigger, not a prompt

The run starts from the data: every customer with `FLAGGED` / `BLOCKED` activity inside the lookback window, grouped by typology, ordered by risk rating and exposure. Three knobs:

- **`ALERT_LOOKBACK_DAYS`** — how far back "incoming" reaches.
- **`TRIAGE_LIMIT`** — how many alerts this run works.
- **`IGNORE_WATERMARK`** — set it to `False` and the desk only works alerts newer than the last recorded run, so a second run in the same window honestly reports **0 new alerts**.

The seeded bank has **130+ alerts**, true positives by construction, so expect an ESCALATE-heavy first run. A production queue is the mirror image — which is why a dismissal has to be written down with a reason."""


P12_QUEUE_CODE = '''# §12.3 — Build the queue. This is the "incoming data" the desk reacts to.
ALERT_LOOKBACK_DAYS = 30     # window of activity this run looks at
TRIAGE_LIMIT        = 3      # alerts to work now; raise after the first pass
IGNORE_WATERMARK    = True   # False -> only alerts newer than the last triage run

ALERT_QUEUE_SQL = """
WITH flagged AS (
  SELECT a.customer_id, t.flag_reason, t.txn_id, t.txn_ts, t.amount_cents, t.channel, t.status
    FROM FINANCE.transactions t
    JOIN FINANCE.accounts a ON a.account_id = t.account_id
   WHERE t.status IN ('FLAGGED','BLOCKED') AND t.flag_reason IS NOT NULL
     AND t.txn_ts >= SYSTIMESTAMP - NUMTODSINTERVAL(:days, 'DAY')
)
SELECT f.customer_id, cu.full_name, cu.segment, cu.country, cu.risk_rating,
       f.flag_reason AS typology,
       COUNT(*) AS flagged_txns,
       SUM(f.amount_cents) AS exposure_cents,
       MIN(f.txn_ts) AS window_start, MAX(f.txn_ts) AS window_end,
       COUNT(DISTINCT f.channel) AS channels,
       SUM(CASE WHEN f.status = 'BLOCKED' THEN 1 ELSE 0 END) AS blocked_txns,
       (SELECT COUNT(*) FROM FINANCE.sar_reports s WHERE s.customer_id = f.customer_id) AS prior_sars
  FROM flagged f
  JOIN FINANCE.customers cu ON cu.customer_id = f.customer_id
 GROUP BY f.customer_id, cu.full_name, cu.segment, cu.country, cu.risk_rating, f.flag_reason
 ORDER BY cu.risk_rating DESC, SUM(f.amount_cents) DESC
"""


def alert_queue(lookback_days=ALERT_LOOKBACK_DAYS, ignore_watermark=IGNORE_WATERMARK):
    """The alerts this run should work, one row per (customer, AML typology)."""
    alerts = _rows(ALERT_QUEUE_SQL, days=lookback_days)
    if not ignore_watermark:
        with agent_conn.cursor() as cur:
            cur.execute("SELECT MAX(window_end) FROM aml_triage")
            watermark = cur.fetchone()[0]
        if watermark:
            print(f"watermark: only alerts newer than {watermark:%Y-%m-%d %H:%M}")
            alerts = [a for a in alerts if a["window_end"] > watermark]
    return alerts


_queue = alert_queue()
print(f"{len(_queue)} alert(s) in the {ALERT_LOOKBACK_DAYS}-day window — "
      f"{_money(sum(a['exposure_cents'] for a in _queue))} of flagged activity, "
      f"{'showing the top ' + str(TRIAGE_LIMIT) if len(_queue) > TRIAGE_LIMIT else 'all'}")
for a in _queue[:TRIAGE_LIMIT]:
    print(f"  [risk {a['risk_rating']:>3}] {a['full_name']:<18} {a['typology']:<18} "
          f"txns={a['flagged_txns']:>2}  exposure={_money(a['exposure_cents']):>14}  "
          f"blocked={a['blocked_txns']}  prior SARs={a['prior_sars']}")'''


P12_EVIDENCE_MD = """## 12.4 The evidence pack — what the model is allowed to see

Assembled in SQL, and the *only* thing the model receives: the alert header, the flagged transactions, the surrounding activity that gives them meaning (the inbound wire before the cash-out, the merchants behind a high-risk corridor), the account history, and the prior SARs. The model does not get to choose its evidence on the happy path — it can only ask for more (`search_knowledge`, `run_sql`) inside its budget. Every decision later in this part is traceable back to lines like these."""


P12_EVIDENCE_CODE = '''# §12.4 — Assemble one alert bundle from SQL. Show the first alert the run will work.
TYPOGRAPHY = {
    "STRUCTURING":       "$10,000 CTR threshold - deposits split just under it, repeated in a short window.",
    "GEO_VELOCITY":      "Impossible travel - one card, far-apart regions, hours apart (card cloning / takeover).",
    "HIGH_RISK_COUNTRY": "Wires to elevated-risk corridors (crypto, gold & forex, casinos, remittance) after an inbound credit.",
    "RAPID_CASH_OUT":    "Large inbound wire, then rapid ATM withdrawals draining the account within ~48 hours.",
    "LARGE_CASH_DEPOSIT": "A single cash deposit above $50,000 with no plausible source of funds.",
}


def evidence_pack(alert, max_txns=8):
    """Everything the agent is allowed to see about one alert. All of it from SQL —
    and all of it scoped to the alert's own window, so the numbers the model reasons
    over match the numbers in the header. Older flagged activity is summarised as
    history instead of being folded into this alert's totals."""
    customer_id, typology = alert["customer_id"], alert["typology"]
    lines = [f"ALERT  customer {customer_id} | {alert['full_name']} | {alert['segment']} | "
             f"{alert['country']} | risk_rating {alert['risk_rating']}/100",
             f"RULE   {typology} — {TYPOGRAPHY.get(typology, '')}",
             f"QUEUE  {alert['flagged_txns']} flagged txn(s), {_money(alert['exposure_cents'])} total, "
             f"{alert['window_start']:%Y-%m-%d} to {alert['window_end']:%Y-%m-%d}, "
             f"{alert['channels']} channel(s), {alert['blocked_txns']} blocked attempt(s)",
             "FLAGGED TRANSACTIONS IN THIS WINDOW (newest first; amounts in USD):"]
    for t in _rows("""
            SELECT t.txn_id, TO_CHAR(t.txn_ts,'YYYY-MM-DD HH24:MI') AS seen_at, t.amount_cents,
                   t.channel, t.txn_type, t.status, t.region, m.name AS merchant
              FROM FINANCE.transactions t
              JOIN FINANCE.accounts a ON a.account_id = t.account_id
              LEFT JOIN FINANCE.merchants m ON m.merchant_id = t.merchant_id
             WHERE a.customer_id = :cid AND t.status IN ('FLAGGED','BLOCKED')
               AND t.flag_reason = :typo AND t.txn_ts >= :wstart
             ORDER BY t.txn_ts DESC FETCH FIRST :n ROWS ONLY""",
                 cid=customer_id, typo=typology, wstart=alert["window_start"], n=max_txns):
        lines.append(f"  txn {t['txn_id']:>5}  {t['seen_at']}  {_money(t['amount_cents']):>13}  "
                     f"{t['channel']}/{t['txn_type']}  status={t['status']}  "
                     f"region={t['region']}  merchant={t['merchant'] or '-'}")

    history = _rows("""
            SELECT COUNT(*) AS older_txns,
                   TO_CHAR(MIN(t.txn_ts),'YYYY-MM-DD') AS first_seen,
                   TO_CHAR(MAX(t.txn_ts),'YYYY-MM-DD') AS last_seen
              FROM FINANCE.transactions t
              JOIN FINANCE.accounts a ON a.account_id = t.account_id
             WHERE a.customer_id = :cid AND t.status IN ('FLAGGED','BLOCKED')
               AND (t.flag_reason <> :typo OR t.flag_reason IS NULL OR t.txn_ts < :wstart)""",
                     cid=customer_id, typo=typology, wstart=alert["window_start"])[0]
    if history["older_txns"]:
        lines.append(f"FLAGGED HISTORY (outside this window): {history['older_txns']} earlier flagged "
                     f"txn(s), {history['first_seen']} to {history['last_seen']} — context only; the "
                     f"window above is what this decision covers.")

    lines.append("RECENT ACTIVITY, ANY STATUS (top 6 by amount, last 30 days — this is the context a "
                 "single flagged row cannot carry):")
    for t in _rows("""
            SELECT t.txn_id, TO_CHAR(t.txn_ts,'YYYY-MM-DD HH24:MI') AS seen_at, t.amount_cents,
                   t.channel, t.txn_type, t.status, m.name AS merchant
              FROM FINANCE.transactions t
              JOIN FINANCE.accounts a ON a.account_id = t.account_id
              LEFT JOIN FINANCE.merchants m ON m.merchant_id = t.merchant_id
             WHERE a.customer_id = :cid AND t.txn_ts >= SYSTIMESTAMP - INTERVAL '30' DAY
             ORDER BY t.amount_cents DESC FETCH FIRST 6 ROWS ONLY""", cid=customer_id):
        lines.append(f"  txn {t['txn_id']:>5}  {t['seen_at']}  {_money(t['amount_cents']):>13}  "
                     f"{t['channel']}/{t['txn_type']}  status={t['status']}  "
                     f"merchant={t['merchant'] or '-'}")

    for a in _rows("""
            SELECT a.account_id, a.account_type, a.currency, a.balance_cents, b.city, b.region
              FROM FINANCE.accounts a JOIN FINANCE.branches b ON b.branch_id = a.branch_id
             WHERE a.customer_id = :cid ORDER BY a.opened_ts""", cid=customer_id):
        lines.append(f"ACCOUNT #{a['account_id']} {a['account_type']} {a['currency']} "
                     f"balance {_money(a['balance_cents'])} ({a['city']}, {a['region']})")

    flow = _rows("""
            SELECT SUM(CASE WHEN t.txn_type IN ('DEPOSIT','WIRE_IN') THEN t.amount_cents ELSE 0 END) AS money_in,
                   SUM(CASE WHEN t.txn_type IN ('WITHDRAWAL','WIRE_OUT') THEN t.amount_cents ELSE 0 END) AS money_out
              FROM FINANCE.transactions t JOIN FINANCE.accounts a ON a.account_id = t.account_id
             WHERE a.customer_id = :cid AND t.txn_ts >= SYSTIMESTAMP - INTERVAL '30' DAY""",
                 cid=customer_id)[0]
    lines.append(f"30-DAY FLOW: money-in {_money(flow['money_in'])} | money-out {_money(flow['money_out'])}")

    for s in _rows("""
            SELECT sar_id, reason_code, status, TO_CHAR(filed_ts,'YYYY-MM-DD') AS filed,
                   SUBSTR(narrative, 1, 180) AS narrative
              FROM FINANCE.sar_reports WHERE customer_id = :cid ORDER BY filed_ts DESC""",
                   cid=customer_id):
        lines.append(f"PRIOR SAR {s['sar_id']}: {s['reason_code']} status={s['status']} "
                     f"filed {s['filed']} — {s['narrative']}")
    return "\\n".join(lines)


_sample_pack = evidence_pack(_queue[0])
print(_sample_pack)
print(f"\\n[{len(_sample_pack.splitlines())} lines, {len(_sample_pack)} chars — "
      f"the model's entire view of this customer]")'''


P12_POLICY_MD = """## 12.5 The decision policy — three verbs and a JSON contract

| Decision | What it authorises | What drives it |
|---|---|---|
| `ESCALATE` | recommend a SAR (new, or an update to an open one) | repetition, blocked attempts, prior SAR, threshold proximity |
| `KYC_REVIEW` | investigate before filing — source-of-funds request, KYC refresh | a real signal on thin evidence |
| `DISMISS` | close the alert **with a written reason** an examiner would accept | activity explained by legitimate behaviour |

The model returns JSON; the harness validates it. Two rules matter:

1. A decision outside the vocabulary becomes **`REVIEW_REQUIRED`** — a human works it. Not an exception, not a silent pass-through.
2. An unknown `sar_reason_code` falls back to the alert's own typology. *The model owns the reasoning; the harness owns the enum.*"""


P12_POLICY_CODE = '''# §12.5 — The policy the model works under, and the validator that enforces it.
TRIAGE_SYSTEM_PROMPT = """You are the Meridian Bank AML triage analyst operating inside an agent harness.
You receive ONE alert. Decide what the bank should do with it.

Decide exactly one:
  ESCALATE   — the evidence meets the filing bar: recommend a SAR (new, or an update to an open one).
  KYC_REVIEW — a real signal, but not enough to file: request source-of-funds / refresh KYC.
  DISMISS    — the activity is explained by legitimate behaviour; write down why an examiner would agree.

Rules:
- Consult your memory first: call search_knowledge for this customer's prior case decisions and the schema
  notes before you decide, and call run_sql if the evidence leaves a question the SQL can answer.
- Judge only the evidence provided; never invent customers, accounts, or amounts.
- Quantify: cite transaction ids and USD amounts (amounts in the alert are already in dollars).
- Weigh repetition, blocked attempts, proximity to reporting thresholds ($10,000 CTR / $50,000),
  prior SARs, and risk_rating.
- If the evidence is thin, say so and choose KYC_REVIEW.

Reply with ONE JSON object and nothing else:
{"decision":"ESCALATE|KYC_REVIEW|DISMISS","confidence":0.0-1.0,"rationale":"<=60 words, cite txn ids and $ amounts",
 "indicators":["..."],"recommended_next_action":"one sentence",
 "sar_reason_code":"STRUCTURING|GEO_VELOCITY|HIGH_RISK_COUNTRY|RAPID_CASH_OUT|LARGE_CASH_DEPOSIT|null"}"""

DECISIONS = ("ESCALATE", "KYC_REVIEW", "DISMISS")


def _extract_json(text):
    """Models wrap JSON in prose often enough that the harness must not trust `json.loads`."""
    match = re.search(r"\\{.*\\}", text or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        try:
            return json.loads(re.sub(r"\\s+", " ", match.group(0)))
        except json.JSONDecodeError:
            return None


def _validate_decision(payload, alert):
    """Clamp whatever the model said to something the bank allows. Never raises."""
    if not isinstance(payload, dict):
        return {"decision": "REVIEW_REQUIRED", "confidence": 0.0,
                "rationale": "Model reply was not valid JSON; a human must work this alert.",
                "indicators": [], "recommended_next_action": "Human review of the raw reply.",
                "sar_reason_code": alert["typology"]}
    decision = str(payload.get("decision", "")).strip().upper()
    if decision not in DECISIONS:
        decision = "REVIEW_REQUIRED"
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(payload.get("sar_reason_code") or "").strip().upper()
    if reason not in TYPOGRAPHY:
        reason = alert["typology"]           # the harness owns the enum
    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": str(payload.get("rationale") or "")[:900],
        "indicators": [str(i)[:60] for i in (payload.get("indicators") or [])][:6],
        "recommended_next_action": str(payload.get("recommended_next_action") or "")[:380],
        "sar_reason_code": reason,
    }


for _probe, _expected in [({"decision": "escalate", "confidence": 1.7, "sar_reason_code": "made_up"}, "ESCALATE"),
                          ("not json at all", "REVIEW_REQUIRED")]:
    _got = _validate_decision(_probe, {"typology": "STRUCTURING"})["decision"]
    assert _got == _expected, f"validator drift: {_got} != {_expected}"
print("✅ decision validator holds: unknown decisions become REVIEW_REQUIRED, confidence is clamped, "
      "reason codes are restricted to the bank's typologies")'''


P12_TRIAGE_MD = """## 12.6 `triage_alert` — the decision, recorded

One alert in, one ledger row and one memory out. The function reuses **`agent_turn`** — the loop from TODO 9 — unchanged: same context assembly, same tool dispatch, same budgets. **Autonomy is not a different loop**; it is the same loop with a trigger and a record.

Three details are the difference between a demo and something a bank could run: the triage instruction travels in the **user message** (so the loop stays reusable, and the thread remembers the alerts it already worked); every decision is written **twice on purpose** (`AML_TRIAGE` for the examiner, a `case_decision` memory for the agent's next run); and model calls are **metered** so §12.8 can report what autonomy cost."""


P12_TRIAGE_CODE = '''# §12.6 — Meter the model, then work one alert end to end.
_USAGE = {"calls": 0, "tokens": 0, "seconds": 0.0}

if not globals().get("_CHAT_METERED"):
    _unmetered_chat = chat

    def chat(*args, **kwargs):                     # noqa: F811 — metered wrapper around the Part 1 client
        started = time.time()
        response = _unmetered_chat(*args, **kwargs)
        _USAGE["calls"] += 1
        _USAGE["seconds"] += time.time() - started
        _USAGE["tokens"] += getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
        return response

    _CHAT_METERED = True
print("model-call meter installed — every LLM round-trip from here on is counted")

TRIAGE_THREAD = "aml-triage-desk"


def triage_alert(alert, thread_id=TRIAGE_THREAD, verbose=True):
    """Work one alert: the agent decides, the harness validates and records."""
    prompt = (TRIAGE_SYSTEM_PROMPT + "\\n\\n--- ALERT ---\\n" + evidence_pack(alert)
              + "\\n--- END ALERT ---\\nDecide now. Reply with the JSON object only.")
    reply = agent_turn(prompt, thread_id=thread_id, max_iterations=6, budget_seconds=120.0, verbose=verbose)
    decision = _validate_decision(_extract_json(reply), alert)

    with agent_conn.cursor() as cur:
        cur.execute("""
            MERGE INTO aml_triage t
            USING (SELECT :cid AS customer_id, :typo AS typology FROM dual) s
               ON (t.customer_id = s.customer_id AND t.typology = s.typology)
            WHEN MATCHED THEN UPDATE SET
                 customer_name = :name, risk_rating = :risk, flagged_txns = :n,
                 exposure_cents = :exp, window_start = :ws, window_end = :we,
                 decision = :dec, confidence = :conf, rationale = :rat,
                 next_action = :nxt, sar_reason = :sar,
                 decided_at = SYSTIMESTAMP, decided_by = :actor
            WHEN NOT MATCHED THEN INSERT
                 (customer_id, typology, customer_name, risk_rating, flagged_txns, exposure_cents,
                  window_start, window_end, decision, confidence, rationale, next_action, sar_reason,
                  decided_at, decided_by)
                 VALUES (:cid, :typo, :name, :risk, :n, :exp, :ws, :we, :dec, :conf, :rat, :nxt, :sar,
                         SYSTIMESTAMP, :actor)""",
            cid=alert["customer_id"], typo=alert["typology"], name=alert["full_name"],
            risk=alert["risk_rating"], n=alert["flagged_txns"], exp=alert["exposure_cents"],
            ws=alert["window_start"], we=alert["window_end"], dec=decision["decision"],
            conf=decision["confidence"], rat=decision["rationale"],
            nxt=decision["recommended_next_action"], sar=decision["sar_reason_code"],
            actor="aml-triage-harness")
    agent_conn.commit()

    write_facts([Fact(
        kind="case_decision",
        subject=f"case:{alert['customer_id']}:{alert['typology']}",
        body=(f"AML triage {decision['decision']} for customer {alert['customer_id']} "
              f"({alert['full_name']}, risk {alert['risk_rating']}/100), typology {alert['typology']}, "
              f"exposure {_money(alert['exposure_cents'])}: {decision['rationale']} "
              f"Next action: {decision['recommended_next_action']}"),
        metadata={"source": "aml_triage", "decision": decision["decision"],
                  "typology": alert["typology"], "customer_id": int(alert["customer_id"]),
                  "confidence": decision["confidence"]},
    )])
    return {**alert, **decision}


print("triage_alert ready — agent_turn decides, the ledger and OAMP memory record")'''


P12_RUN_MD = """## 12.7 Run it — the bank's morning queue

Three alerts by default, each a full model round-trip inside the bounded loop. The run prints one line per alert — decision, confidence, reason — then dumps the ledger as an examiner's SQL client would read it. A failure inside one alert is recorded and the run moves on: the difference between "the desk ran" and "the desk stopped because one customer's data was odd"."""


P12_RUN_CODE = '''# §12.7 — Work the queue and print the ledger.
def run_triage(alerts=None, limit=TRIAGE_LIMIT, thread_id=TRIAGE_THREAD):
    queue = list(alerts if alerts is not None else alert_queue())[:limit]
    if not queue:
        print("Queue empty — no alerts in the lookback window "
              "(set IGNORE_WATERMARK = True in §12.3 to re-triage the same window).")
        return []
    records, failures = [], []
    started = time.time()
    for i, alert in enumerate(queue, 1):
        print(f"\\n[{i}/{len(queue)}] customer {alert['customer_id']} · {alert['typology']} · "
              f"{_money(alert['exposure_cents'])} flagged exposure")
        try:
            record = triage_alert(alert, thread_id=thread_id)
        except Exception as exc:                    # one bad alert must not end the desk's morning
            failures.append((alert, exc))
            print(f"   ! triage failed: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        records.append(record)
        print(f"   -> {record['decision']:<16} confidence {record['confidence']:.2f}")
        print(f"      {record['rationale']}")
        print(f"      next: {record['recommended_next_action']}")
    print(f"\\n{len(records)} decision(s) in {time.time() - started:.0f}s · "
          f"{_USAGE['calls']} model call(s) · {_USAGE['tokens']:,} tokens")
    if failures and not records:
        print("\\nEvery alert failed. If the traceback says a TODO is still a stub, finish the TODOs "
              "above before running Part 12.")
    return records


_records = run_triage()

print("\\nLedger — AGENT.AML_TRIAGE (what a reviewer or examiner would query):")
for row in _rows("""
        SELECT customer_id, customer_name, typology, decision, confidence,
               exposure_cents, next_action
          FROM aml_triage ORDER BY decided_at DESC"""):
    print(f"  cust {row['customer_id']:>3}  {row['customer_name']:<18} {row['typology']:<18} "
          f"{row['decision']:<16} conf {row['confidence']:.2f}  {_money(row['exposure_cents']):>14}  "
          f"{(row['next_action'] or '')[:60]}")'''


P12_IMPACT_MD = """## 12.8 The impact board — what this is worth to Meridian Bank

An AML programme is measured on a short list: alerts worked, time-to-decision, filings made, evidence that survives an examination — and what it costs in people to produce all three. The board computes those numbers from the ledger and `FINANCE`.

One input cannot come from the database, so it is a labelled knob: `MANUAL_MINUTES_PER_ALERT` (45 by default — change it and re-run). Everything above that row is computed, and the last block states plainly what the harness did **not** do."""


P12_IMPACT_CODE = '''# §12.8 — The morning briefing, computed from the ledger + FINANCE.
MANUAL_MINUTES_PER_ALERT = 45.0   # ASSUMPTION, not a measurement — change it and re-run.

_by_decision = _rows("""
        SELECT decision, COUNT(*) AS alerts, SUM(exposure_cents) AS exposure_cents
          FROM aml_triage GROUP BY decision ORDER BY alerts DESC, exposure_cents DESC""")
_total_alerts = sum(r["alerts"] for r in _by_decision)
_decision_of = {r["decision"]: r for r in _by_decision}
_escalated = _decision_of.get("ESCALATE", {"alerts": 0, "exposure_cents": 0})
_review = _decision_of.get("REVIEW_REQUIRED", {"alerts": 0, "exposure_cents": 0})
_confidence = _rows("SELECT ROUND(AVG(confidence), 2) AS avg_conf FROM aml_triage "
                    "WHERE decision <> 'REVIEW_REQUIRED'")[0]["avg_conf"]
_sars = _rows("SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'FILED' THEN 1 ELSE 0 END) AS filed "
              "FROM finance.sar_reports")[0]
_ages = _rows("SELECT ROUND(MAX(CAST(SYSTIMESTAMP AS DATE) - CAST(window_end AS DATE))) AS oldest, "
              "       ROUND(AVG(CAST(SYSTIMESTAMP AS DATE) - CAST(window_end AS DATE))) AS average "
              "  FROM aml_triage")[0]
_age_line = (f"{int(_ages['oldest'])}d  (avg {int(_ages['average'])}d)"
             if _ages["oldest"] is not None else "n/a — the ledger is empty; run §12.7 first")
_manual_hours = _total_alerts * MANUAL_MINUTES_PER_ALERT / 60.0

print("MERIDIAN BANK · AML ALERT TRIAGE · MORNING BRIEFING")
print("=" * 72)
print(f"  alerts decided by the harness .......... {_total_alerts}")
for row in _by_decision:
    bar = "█" * max(1, int(32 * row["alerts"] / max(_total_alerts, 1)))
    print(f"    {row['decision']:<16} {row['alerts']:>3}  {bar}  {_money(row['exposure_cents'])}")
print(f"  flagged exposure escalated to compliance {_money(_escalated['exposure_cents'])}")
print(f"  average confidence on decided alerts ... {_confidence if _confidence is not None else 'n/a'}")
print(f"  oldest alert worked (now - newest txn) . {_age_line}")
print("-" * 72)
print(f"  harness cost ........................... {_USAGE['calls']} model call(s) · "
      f"{_USAGE['tokens']:,} tokens · {_USAGE['seconds']:.0f}s of model wall-clock")
print(f"  equivalent manual effort ............... {_manual_hours:.1f}h at "
      f"{MANUAL_MINUTES_PER_ALERT:.0f} min/alert (assumption)")
print(f"  SAR history on file .................... {_sars['total']} report(s), {_sars['filed']} filed")
if _review["alerts"]:
    print(f"  human review required .................. {_review['alerts']} alert(s) — "
          f"the model's reply did not validate")
print("=" * 72)
print("What the harness did NOT do: file anything, write to FINANCE, or see data its persona "
      "is not entitled to.")
print("The recommendation is a decision record; a human signs the filing. That boundary is the "
      "reason this can run every morning.")'''


P12_LOOP_MD = """## 12.9 Close the loop — the agent remembers its own decisions

The decisions are memories (`kind="case_decision"`), not just rows, so the same `agent_turn` can answer questions about its own morning — which is the difference between a decision log and a colleague who was there. Watch `search_knowledge` fire: the answer is grounded in the rationales it wrote minutes ago, not re-derived from SQL."""


P12_LOOP_CODE = '''# §12.9 — Ask the agent about its own triage run. No new SQL: this is memory recall.
_question = ("You triaged part of Meridian Bank's AML alert queue this morning. From your own case "
             "decisions: which customers did you escalate, what is the total exposure now under review, "
             "and which single case should a human reviewer pick up first — and why?")
print("USER:", _question)
print("\\nAGENT:", agent_turn(_question, thread_id=TRIAGE_THREAD, max_iterations=6, budget_seconds=120.0))'''


P12_NEXT_MD = """## 12.10 From one morning to a running programme

| Next step | How, in this stack |
|---|---|
| **Run it every morning** | a `DBMS_SCHEDULER` job, like the app's scan scheduler (`app/backend/db/scheduler_setup.py`) |
| **Make it incremental** | `IGNORE_WATERMARK = False` in §12.3 — the second run of the day reports **0 new alerts** |
| **Keep a human in the loop** | `REVIEW_REQUIRED` already routes unvalidated output to a person; sample a percentage of `DISMISS` decisions |
| **Watch precision, not volume** | `SELECT decision, COUNT(*) FROM aml_triage GROUP BY decision` is the false-positive rate over time |
| **Prove it to an examiner** | every row carries its evidence window, rationale, and confidence — replayable from OAMP |
| **Scope it by identity** | run the desk as `compliance.officer` vs `analyst.east` and the same queue returns different rows ([Part 8](docs/part-8-deep-data-security.md)) |

The honest limits: a model that decides can be wrong at scale, the policy is only as good as its thresholds, and the seeded queue is true-positive-weighted. The claim is not that the agent is right — it is that its judgement arrives with **evidence, a reason, a record, and a budget**.

**See it as a product:** [http://localhost:3000](http://localhost:3000) runs on the same store this notebook just wrote to."""


CLOSING_MARKER = "# The capstone — decisions, not just answers"

CLOSING_ADDITION = """# The capstone — decisions, not just answers

**Part 12** turned the harness outward: it worked Meridian Bank's AML alert queue end to end, decided with a reason and a confidence, wrote every decision to `AGENT.AML_TRIAGE` and to memory, and reported what the run was worth to the bank.

It is the same loop you built in TODO 9. A **trigger**, a **record**, and a **budget** are what turn a chat window into something a compliance desk could run every morning — and the split between the model's judgement and the harness's state is what makes it auditable."""


# --------------------------------------------------------------------------
# Notebook assembly
# --------------------------------------------------------------------------
def build_orientation() -> list[dict]:
    return [md(SELF_CHECK_MD), code(SELF_CHECK)]


def build_preflight() -> list[dict]:
    return [md(PREFLIGHT_MD), code(PREFLIGHT_CODE)]


def build_part12() -> list[dict]:
    return [
        md(P12_INTRO_MD), code(P12_GATE_CODE),
        md(P12_DATA_MD),
        md(P12_LEDGER_MD), code(P12_LEDGER_CODE),
        md(P12_QUEUE_MD), code(P12_QUEUE_CODE),
        md(P12_EVIDENCE_MD), code(P12_EVIDENCE_CODE),
        md(P12_POLICY_MD), code(P12_POLICY_CODE),
        md(P12_TRIAGE_MD), code(P12_TRIAGE_CODE),
        md(P12_RUN_MD), code(P12_RUN_CODE),
        md(P12_IMPACT_MD), code(P12_IMPACT_CODE),
        md(P12_LOOP_MD), code(P12_LOOP_CODE),
        md(P12_NEXT_MD),
    ]


def drop_blocks(cells: list[dict], names: tuple[str, ...]) -> list[dict]:
    """Remove these blocks (and their sentinels) from the notebook entirely."""
    for name in names:
        cells, _ = _without_block(cells, name)
    return cells


def append_closing(cells: list[dict]) -> None:
    index = find_cell(cells, CLOSE_ANCHOR)
    source = "".join(cells[index]["source"])
    head = source.split(CLOSING_MARKER)[0].rstrip()
    if head.endswith("---"):
        head = head[:-3].rstrip()
    cells[index]["source"] = (head + "\n\n---\n\n" + CLOSING_ADDITION).splitlines(keepends=True)


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save(path: Path, notebook: dict) -> None:
    path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")




def update_lightweight(path: Path) -> None:
    notebook = load(path)
    cells = drop_blocks(notebook["cells"], ("start-here", "contents"))

    # Pull the blocks we own out first — and remember what they held, so cells
    # whose source did not change keep their outputs (see merge_block).
    previous = {}
    for name in ("self-check", "preflight", "part-12"):
        cells, previous[name] = _without_block(cells, name)

    title_at = find_cell(cells, "# Financial Data Agent Workshop")
    cells = (cells[:title_at + 1] + merge_block("self-check", build_orientation(), previous["self-check"])
             + cells[title_at + 1:])
    connect_at = find_cell(cells, CONNECT_ANCHOR)
    cells = (cells[:connect_at + 1] + merge_block("preflight", build_preflight(), previous["preflight"])
             + cells[connect_at + 1:])
    close_at = find_cell(cells, CLOSE_ANCHOR)
    cells = (cells[:close_at] + merge_block("part-12", build_part12(), previous["part-12"])
             + cells[close_at:])
    append_closing(cells)

    notebook["cells"] = cells
    save(path, notebook)
    print(f"{path.name}: {len(cells)} cells")




def main() -> int:
    update_lightweight(STUDENT)
    update_lightweight(COMPLETE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())