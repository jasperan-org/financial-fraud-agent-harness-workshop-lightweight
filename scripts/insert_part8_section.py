"""Insert the Part 8 (identity-aware data access) section into the reference
notebook, immediately before Part 9. Run from the repository root."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "enterprise_data_agent.ipynb"

MD_INTRO = r"""## Part 8 — Identity-aware data access: putting the boundary in the kernel

*Parts 4–7 gave the agent memory. Before Part 9 hands it compute, this part answers a
harder question: **what is the agent allowed to see, and who decides?***

The harness already has personas — the `Use As:` dropdown in the app
(`app/backend/api/identities.py`). Each carries a clearance, a set of authorized
regions, columns to redact, and tables to refuse. The interesting question is not
*which* rules exist. It is **where they are enforced**.

If the rules live in Python, then the database has already handed over the rows by the
time they apply. The agent asked for `SELECT * FROM FINANCE.TRANSACTIONS`, Oracle
returned every region, and a `for` loop in Flask threw some away. That is not a security
boundary. It is a UI preference with a security-shaped comment above it — and it holds
only as long as no one finds a path around the loop.

### The bug that proves the point

This repository's own persona registry declared this mask:

```python
_ACCOUNT_IDENTIFIER_MASKS = ["FINANCE.ACCOUNTS.ACCOUNT_NUMBER", ...]
```

`FINANCE.ACCOUNTS` has no `ACCOUNT_NUMBER` column. It never did — the account
identifier is the numeric `ACCOUNT_ID`, and the sensitive value on that table is
`BALANCE_CENTS`. In Python the rule failed **silently**: a mask naming a column that
does not exist is indistinguishable from a mask that works. The moment the same rule is
pushed into the database (Part 8.4) Oracle rejects it outright:

```
ORA-23607: invalid column "ACCOUNT_NUMBER"
```

That is the whole argument for this part. A rule the kernel cannot compile is a rule you
find out about. A rule the application "applies" is a rule you find out about in the
incident review.
"""

MD_WHAT = r"""### What Oracle Deep Data Security is

Oracle Deep Data Security (**Deep Sec**) is the database-native authorization model
introduced in **Oracle AI Database 26ai** for exactly this problem — agents and
applications querying on behalf of an end user.

- **Data grants** (`CREATE DATA GRANT`) authorize `SELECT/UPDATE/INSERT/DELETE` on an
  object, optionally narrowed by a `WHERE` predicate and to a column list. They are
  **additive** and **default-deny**: no grant means no access.
- **Data roles** (`CREATE DATA ROLE`) map to roles in an external IAM (OCI IAM, Entra ID)
  or are managed locally in the database.
- **End users** (`CREATE END USER`) do not own schemas. They are the application's
  users — the personas in this workshop.
- **End-user security context** travels with each request. The client driver attaches it:
  `oracledb.create_end_user_security_context(end_user_identity=..., database_access_token=..., data_roles=[...])`.
- **Access-check functions** let a query ask about itself:
  `ORA_IS_COLUMN_AUTHORIZED(ssn)` distinguishes a genuine `NULL` from a masked one, and
  `ORA_CHECK_DATA_PRIVILEGE(emp, 'UPDATE', phone)` answers "may I?" *before* the
  statement runs.

The point is that the agent no longer has to be trusted. It can emit the broadest SQL it
likes — the kernel returns the rows its end user is entitled to, and nothing else.

### What this exercise database can enforce

Deep Sec is an Enterprise-class feature. The workshop runs **Oracle AI Database 26ai
Free** in a container, so this part teaches the shape of the real thing and then
implements the same semantics with what the Free edition does have: an application
context plus `DBMS_RLS` (row/column VPD). Two cells below prove the difference rather
than asserting it.
"""

MD_BACKENDS = r"""### Two backends, one rule set

| | `DEEP_SEC` | `VPD` (this notebook) | `APP_ONLY` |
|---|---|---|---|
| **Requires** | 26ai Enterprise-class (Base DB, Exadata, Autonomous AI Database) + IAM tokens | 26ai Free and older, `DBMS_RLS` | nothing |
| **Rows** | `CREATE DATA GRANT ... WHERE <predicate>` | `DBMS_RLS.ADD_POLICY` + app context | Python drops rows after fetch |
| **Columns** | omitted columns return `NULL` | `sec_relevant_cols` + `ALL_ROWS` returns `NULL` | Python overwrites with `[REDACTED]` |
| **Default** | default-deny | **fail-open** unless a predicate says otherwise | fail-open |
| **Trust boundary** | the kernel | the kernel | the application |

Two honest caveats, because a security demo that overstates itself is worse than none:

1. **The VPD path is fail-open.** With no end-user context set,
   `SYS_CONTEXT('EDA_CTX','END_USER')` is `NULL` and the predicates evaluate to `1=1`.
   Every row is visible. Deep Sec is default-deny. Closing that gap on Free means
   auditing which sessions set a context — the code below sets it on every read path,
   which is exactly why Part 8.6 wires it into the agent's `run_sql` tool.
2. **A VPD predicate may not subquery another policied table.** Nesting
   `SELECT ... FROM FINANCE.branches` inside a policy on `FINANCE.accounts` raises
   `ORA-28113`, because `branches` carries a policy of its own. The fix is the standard
   one: precompute the reachable keys into an unprotected table (`AGENT.agent_scope`)
   and keep predicates to a plain `EXISTS` against it.
"""

CODE_PROBE = r'''# ---- 8.1  Ask the database what it can enforce ------------------------------
# Every check is a dictionary query, so this is safe on any edition.

with agent_conn.cursor() as cur:
    def one(sql, **b):
        cur.execute(sql, b or None)
        return cur.fetchone()[0]

    release = one("SELECT banner_full FROM v$version")
    has_deep_sec = one("SELECT COUNT(*) FROM all_objects "
                       " WHERE object_name LIKE 'DBMS_DEEP_SEC%'")
    has_grants = one("SELECT COUNT(*) FROM all_views WHERE view_name IN "
                     " ('DBA_DATA_GRANTS','ALL_DATA_GRANTS','DBA_DATA_ROLES','DBA_END_USERS')")
    has_rls = one("SELECT COUNT(*) FROM all_objects "
                  " WHERE object_name LIKE 'DBMS_RLS%'")

backend = "DEEP_SEC" if (has_deep_sec and has_grants) else "VPD" if has_rls else "APP_ONLY"

print(f"release            : {release.splitlines()[0]}")
print(f"DBMS_DEEP_SEC      : {'present' if has_deep_sec else 'ABSENT'}")
print(f"data-grant views   : {'present' if has_grants else 'ABSENT'}")
print(f"DBMS_RLS           : {'present' if has_rls else 'ABSENT'}")
print(f"=> enforcement     : {backend}")
'''

CODE_REJECTED = r'''# ---- 8.2  Prove the Free edition cannot run Deep Sec ------------------------
# Not a guess and not a doc quote: these are the four DDL forms Deep Sec is built
# from, executed against the live database.

DEEP_SEC_DDL_PROBE = [
    "CREATE DATA ROLE eda_probe_role",
    "CREATE END USER eda_probe_user",
    "CREATE DATA GRANT eda_probe_grant AS SELECT ON FINANCE.TRANSACTIONS TO eda_probe_role",
    "CREATE DATA SECURITY POLICY eda_probe_policy ON FINANCE.TRANSACTIONS USING (1=1)",
]

for stmt in DEEP_SEC_DDL_PROBE:
    try:
        with agent_conn.cursor() as cur:
            cur.execute(stmt)
        print(f"  accepted : {stmt}")
    except oracledb.DatabaseError as e:
        print(f"  REJECTED : ORA-{e.args[0].code:<6} {stmt}")

print("\n=> Deep Sec needs a 26ai Enterprise-class database; this notebook builds the")
print("   equivalent enforcement from DBMS_RLS so the demo still shows real kernel checks.")
'''

CODE_RULES = r'''# ---- 8.3  One rule set, expressed as data ----------------------------------
# Same six personas as the app's `Use As:` dropdown. Rules go into tables, not
# into Python branches, so changing who sees what is an INSERT — no redeploy.

DOMAIN = "meridianbank.example"

_PII       = ["FINANCE.CUSTOMERS.SSN"]
_MONEY     = ["FINANCE.ACCOUNTS.BALANCE_CENTS",
              "FINANCE.CARDS.CARD_NUMBER",
              "FINANCE.TRANSACTIONS.AMOUNT_CENTS"]
_NARRATIVE = ["FINANCE.SAR_REPORTS.NARRATIVE"]

PERSONAS = {
    "agent":              dict(clearance="STANDARD",  regions=None,
                               masks=_PII + _MONEY + _NARRATIVE,
                               denies=["FINANCE.SAR_REPORTS"]),
    "cfo":                dict(clearance="EXECUTIVE", regions=None, masks=[],
                               denies=["FINANCE.SAR_REPORTS"]),
    "compliance.officer": dict(clearance="EXECUTIVE", regions=None, masks=[],
                               denies=[]),
    "analyst.east":       dict(clearance="STANDARD",  regions=["EUROPE", "MIDDLE_EAST"],
                               masks=_PII + _MONEY + _NARRATIVE,
                               denies=["FINANCE.SAR_REPORTS"]),
    "analyst.west":       dict(clearance="STANDARD",  regions=["AMERICAS", "ASIA_PACIFIC"],
                               masks=_PII + _MONEY + _NARRATIVE,
                               denies=["FINANCE.SAR_REPORTS"]),
    "ops.viewer":         dict(clearance="STANDARD",  regions=None, masks=_MONEY,
                               denies=["FINANCE.CUSTOMERS", "FINANCE.SAR_REPORTS"]),
}


def end_user(pid: str) -> str:
    return f"{pid}@{DOMAIN}"


print(f"{'persona':<20} {'clearance':<10} {'regions':<26} masks  denies")
print("-" * 74)
for pid, p in PERSONAS.items():
    regions = ",".join(p["regions"]) if p["regions"] else "(all)"
    print(f"{pid:<20} {p['clearance']:<10} {regions:<26} "
          f"{len(p['masks']):>5}  {len(p['denies']):>6}")
'''

CODE_INSTALL = r'''# ---- 8.4  Install the enforcement ------------------------------------------
# Rows:    AGENT.agent_authorizations  (region membership per end user)
# Columns: AGENT.agent_masks            (which columns to blank)
# Denials: AGENT.agent_denials          (tables nobody may read)
# Scope:   AGENT.agent_scope            (precomputed keys — see the caveat above)
#
# Idempotent: safe to re-run.

RULE_TABLES = {
    "agent_authorizations":
        "CREATE TABLE agent_authorizations (end_user VARCHAR2(128) NOT NULL, "
        "auth_region VARCHAR2(32) NOT NULL)",
    "agent_clearances":
        "CREATE TABLE agent_clearances (end_user VARCHAR2(128) NOT NULL, "
        "clearance VARCHAR2(32) NOT NULL, notes VARCHAR2(400))",
    "agent_masks":
        "CREATE TABLE agent_masks (end_user VARCHAR2(128) NOT NULL, "
        "owner VARCHAR2(64) NOT NULL, table_name VARCHAR2(128) NOT NULL, "
        "column_name VARCHAR2(128) NOT NULL)",
    "agent_denials":
        "CREATE TABLE agent_denials (end_user VARCHAR2(128) NOT NULL, "
        "owner VARCHAR2(64) NOT NULL, table_name VARCHAR2(128) NOT NULL)",
    "agent_scope":
        "CREATE TABLE agent_scope (end_user VARCHAR2(128) NOT NULL, "
        "scope_kind VARCHAR2(10) NOT NULL, scope_id NUMBER)",
}

with agent_conn.cursor() as cur:
    for table, ddl in RULE_TABLES.items():
        try:
            cur.execute(ddl)
            print(f"  created {table}")
        except oracledb.DatabaseError as e:
            if e.args[0].code != 955:      # ORA-00955: name is already used
                raise
        cur.execute(f"DELETE FROM {table}")

    for pid, p in PERSONAS.items():
        u = end_user(pid)
        cur.execute(
            "INSERT INTO agent_clearances (end_user, clearance, notes) "
            "VALUES (:u, :c, NULL)", u=u, c=p["clearance"])
        for region in (p["regions"] or ["ALL"]):
            cur.execute(
                "INSERT INTO agent_authorizations (end_user, auth_region) "
                "VALUES (:u, :r)", u=u, r=region)
        for qualified in p["masks"]:
            owner, table, column = qualified.split(".")
            cur.execute(
                "INSERT INTO agent_masks (end_user, owner, table_name, column_name) "
                "VALUES (:u, :o, :t, :c)", u=u, o=owner, t=table, c=column)
        for qualified in p["denies"]:
            owner, table = qualified.split(".")
            cur.execute(
                "INSERT INTO agent_denials (end_user, owner, table_name) "
                "VALUES (:u, :o, :t)", u=u, o=owner, t=table)
agent_conn.commit()
print("  rules loaded")

# The predicates run as FINANCE, so it must be able to read the rule tables.
with agent_conn.cursor() as cur:
    for table in ("AGENT_AUTHORIZATIONS", "AGENT_CLEARANCES", "AGENT_MASKS",
                  "AGENT_DENIALS", "AGENT_SCOPE"):
        cur.execute(f"GRANT SELECT ON {table} TO FINANCE")
    cur.execute("GRANT INSERT, DELETE ON AGENT_SCOPE TO FINANCE")
agent_conn.commit()
print("  granted reads to FINANCE")

# The trusted setter: the only code allowed to write the EDA_CTX namespace, so a
# caller cannot simply declare itself the CFO.
with agent_conn.cursor() as cur:
    cur.execute("""
    CREATE OR REPLACE PROCEDURE set_eda_ctx(
        p_end_user IN VARCHAR2, p_clearance IN VARCHAR2 DEFAULT NULL
    ) AS
        v_clearance VARCHAR2(32);
    BEGIN
        IF p_clearance IS NULL AND p_end_user IS NOT NULL THEN
            BEGIN
                SELECT clearance INTO v_clearance
                  FROM agent_clearances WHERE end_user = p_end_user;
            EXCEPTION WHEN NO_DATA_FOUND THEN v_clearance := 'STANDARD';
            END;
        ELSE
            v_clearance := NVL(p_clearance, 'STANDARD');
        END IF;
        DBMS_SESSION.SET_CONTEXT('EDA_CTX', 'END_USER',  p_end_user);
        DBMS_SESSION.SET_CONTEXT('EDA_CTX', 'CLEARANCE', v_clearance);
    END;
    """)
agent_conn.commit()

created = False
with agent_conn.cursor() as cur:
    try:
        cur.execute("CREATE OR REPLACE CONTEXT eda_ctx USING AGENT.set_eda_ctx")
        created = True
    except oracledb.DatabaseError as e:
        if e.args[0].code not in (1031, 2000, 900, 901, 922):
            raise
if not created:
    with sys_conn.cursor() as cur:
        cur.execute("GRANT CREATE ANY CONTEXT TO AGENT")
        cur.execute("CREATE OR REPLACE CONTEXT eda_ctx USING AGENT.set_eda_ctx")
    sys_conn.commit()
print("  EDA_CTX namespace ready (writable only via AGENT.set_eda_ctx)")
'''

CODE_POLICIES = r'''# ---- 8.5  Attach the policies ------------------------------------------------
# Three predicate shapes cover everything:
#   region  — tables that carry a REGION column
#   scope   — tables reached by a foreign key, via the precomputed agent_scope
#   deny    — tables an end user may not read at all
# plus one tiny function per masked column (DBMS_RLS binds the column to the
# policy, not to the function signature, so each column needs its own).

finance_conn = connect("FINANCE", "FinancePwd_2025", SYS_DSN)

# Precompute reachable branches/accounts/customers per persona. Runs with no
# end-user context set, where every predicate is 1=1, so it sees the full map.
with finance_conn.cursor() as cur:
    cur.execute("DELETE FROM AGENT.agent_scope")
    for pid, p in PERSONAS.items():
        u = end_user(pid)
        if not p["regions"]:
            cur.executemany(
                "INSERT INTO AGENT.agent_scope (end_user, scope_kind, scope_id) "
                "VALUES (:u, :k, NULL)",
                [(u, k) for k in ("BRANCH", "ACCOUNT", "CUSTOMER")])
            continue
        marks = ", ".join(f":r{i}" for i in range(len(p["regions"])))
        binds = {"u": u, **{f"r{i}": r for i, r in enumerate(p["regions"])}}
        cur.execute(
            f"INSERT INTO AGENT.agent_scope (end_user, scope_kind, scope_id) "
            f"SELECT :u, 'BRANCH', b.branch_id FROM FINANCE.branches b "
            f" WHERE b.region IN ({marks})", binds)
        for kind, key in (("ACCOUNT", "a.account_id"), ("CUSTOMER", "a.customer_id")):
            cur.execute(
                f"INSERT INTO AGENT.agent_scope (end_user, scope_kind, scope_id) "
                f"SELECT DISTINCT :u, '{kind}', {key} "
                f"  FROM FINANCE.accounts a JOIN FINANCE.branches b "
                f"    ON b.branch_id = a.branch_id "
                f" WHERE b.region IN ({marks})", binds)
finance_conn.commit()

REGION_FN = """
CREATE OR REPLACE FUNCTION eda_region_predicate(
    p_schema IN VARCHAR2, p_object IN VARCHAR2
) RETURN VARCHAR2 AS
    v_user VARCHAR2(128) := SYS_CONTEXT('EDA_CTX', 'END_USER');
BEGIN
    IF v_user IS NULL THEN RETURN '1=1'; END IF;
    RETURN q'[EXISTS (SELECT 1 FROM AGENT.agent_authorizations a
                      WHERE a.end_user = SYS_CONTEXT('EDA_CTX','END_USER')
                        AND (a.auth_region = 'ALL' OR a.auth_region = region))]';
END;
"""

# A single quote, kept out of the SQL text so this cell stays readable. Getting
# quote escaping wrong here is silent: the predicate compiles, the policy
# installs, and every SELECT then fails with ORA-28113 at query time.
Q = chr(39)

SCOPE_FN = f"""
CREATE OR REPLACE FUNCTION eda_scope_predicate(
    p_schema IN VARCHAR2, p_object IN VARCHAR2
) RETURN VARCHAR2 AS
    v_user VARCHAR2(128) := SYS_CONTEXT({Q}EDA_CTX{Q}, {Q}END_USER{Q});
    v_kind VARCHAR2(10);
    v_key  VARCHAR2(32);
BEGIN
    IF v_user IS NULL THEN RETURN {Q}1=1{Q}; END IF;
    v_kind := CASE p_object WHEN {Q}ACCOUNTS{Q} THEN {Q}BRANCH{Q}
                            WHEN {Q}LOANS{Q}    THEN {Q}BRANCH{Q}
                            WHEN {Q}CARDS{Q}    THEN {Q}ACCOUNT{Q}
                            ELSE {Q}CUSTOMER{Q} END;
    v_key := CASE v_kind WHEN {Q}BRANCH{Q}   THEN {Q}branch_id{Q}
                         WHEN {Q}ACCOUNT{Q}  THEN {Q}account_id{Q}
                         ELSE {Q}customer_id{Q} END;
    -- AGENT.agent_scope holds the keys this end user may reach. The predicate
    -- must not subquery FINANCE.branches: that table carries a policy of its
    -- own, and nesting two policied tables raises ORA-28113.
    RETURN {Q}EXISTS (SELECT 1 FROM AGENT.agent_scope s {Q}
        || {Q} WHERE s.end_user = SYS_CONTEXT({Q}{Q}EDA_CTX{Q}{Q},{Q}{Q}END_USER{Q}{Q}){Q}
        || {Q}   AND s.scope_kind = {Q}{Q}{Q} || v_kind || {Q}{Q}{Q}{Q}
        || {Q}   AND (s.scope_id IS NULL OR s.scope_id = {Q} || LOWER(p_object)
        || {Q}.{Q} || v_key || {Q})){Q};
END;
"""

DENY_FN = """
CREATE OR REPLACE FUNCTION eda_deny_predicate(
    p_schema IN VARCHAR2, p_object IN VARCHAR2
) RETURN VARCHAR2 AS
    v_hit PLS_INTEGER;
BEGIN
    IF SYS_CONTEXT('EDA_CTX', 'END_USER') IS NULL THEN RETURN '1=1'; END IF;
    SELECT COUNT(*) INTO v_hit FROM AGENT.agent_denials d
     WHERE d.end_user = SYS_CONTEXT('EDA_CTX','END_USER')
       AND d.owner = p_schema AND d.table_name = p_object;
    RETURN CASE WHEN v_hit > 0 THEN '1=0' ELSE '1=1' END;
END;
"""

REGION_TABLES  = ["TRANSACTIONS", "BRANCHES", "MERCHANTS"]
SCOPE_TABLES   = ["ACCOUNTS", "LOANS", "CARDS", "CUSTOMERS", "SAR_REPORTS"]
DENY_TABLES    = sorted({q.split(".")[1] for p in PERSONAS.values() for q in p["denies"]})
MASKED_COLUMNS = sorted({tuple(q.split(".")[1:]) for p in PERSONAS.values() for q in p["masks"]})

DROP_POLICY = ("BEGIN DBMS_RLS.DROP_POLICY(object_schema => :s, "
               "object_name => :o, policy_name => :p); END;")
ADD_ROW = ("BEGIN DBMS_RLS.ADD_POLICY(object_schema => :s, object_name => :o, "
           "policy_name => :p, function_schema => :s, policy_function => :f, "
           "statement_types => 'SELECT'); END;")
ADD_MASK = ("BEGIN DBMS_RLS.ADD_POLICY(object_schema => :s, object_name => :o, "
            "policy_name => :p, function_schema => :s, policy_function => :f, "
            "statement_types => 'SELECT', sec_relevant_cols => :c, "
            "sec_relevant_cols_opt => DBMS_RLS.ALL_ROWS); END;")

ALL_TABLES = sorted(set(REGION_TABLES + SCOPE_TABLES + DENY_TABLES))

with finance_conn.cursor() as cur:
    # This cell owns the policies on these tables. Clear whatever a previous run
    # — or app/scripts/setup_deep_security.py — left behind first. Two reasons:
    # a stale policy still points at a predicate function we are about to
    # replace (which raises ORA-28113), and two policies masking the same column
    # is a bug waiting to happen.
    cur.execute("SELECT object_name, policy_name FROM all_policies "
                " WHERE object_owner = 'FINANCE'")
    for obj, pol in cur.fetchall():
        if obj in ALL_TABLES:
            cur.execute(DROP_POLICY, s="FINANCE", o=obj, p=pol)

    cur.execute(REGION_FN)
    cur.execute(SCOPE_FN)
    cur.execute(DENY_FN)

    installed = 0
    # Deny policies get their own name: a table can be BOTH region-scoped and
    # denied (CUSTOMERS is), and reusing one name would make the second policy
    # silently replace the first.
    plan = ([(t, "EDA_REGION_PREDICATE", f"EDA_{t}_POLICY") for t in REGION_TABLES]
            + [(t, "EDA_SCOPE_PREDICATE", f"EDA_{t}_POLICY") for t in SCOPE_TABLES]
            + [(t, "EDA_DENY_PREDICATE", f"EDA_{t}_DENY_POLICY") for t in DENY_TABLES])
    for table, fn, policy in plan:
        try:
            cur.execute(DROP_POLICY, s="FINANCE", o=table, p=policy)
        except oracledb.DatabaseError:
            pass
        cur.execute(ADD_ROW, s="FINANCE", o=table, p=policy, f=fn)
        installed += 1

    # One predicate per masked column: DBMS_RLS hands the function no column
    # name, so the column is baked into a tiny generated function.
    for table, column in MASKED_COLUMNS:
        fn = f"EDA_MASK_{table}_{column}"
        cur.execute(f"""
        CREATE OR REPLACE FUNCTION {fn}(
            p_schema IN VARCHAR2, p_object IN VARCHAR2
        ) RETURN VARCHAR2 AS
            v_hit PLS_INTEGER;
        BEGIN
            IF SYS_CONTEXT('EDA_CTX', 'END_USER') IS NULL THEN RETURN '1=1'; END IF;
            SELECT COUNT(*) INTO v_hit FROM AGENT.agent_masks m
             WHERE m.end_user = SYS_CONTEXT('EDA_CTX','END_USER')
               AND m.owner = p_schema AND m.table_name = '{table}'
               AND m.column_name = '{column}';
            RETURN CASE WHEN v_hit > 0 THEN '1=0' ELSE '1=1' END;
        END;
        """)
        policy = f"{fn}_POLICY"
        try:
            cur.execute(DROP_POLICY, s="FINANCE", o=table, p=policy)
        except oracledb.DatabaseError:
            pass
        cur.execute(ADD_MASK, s="FINANCE", o=table, p=policy, f=fn, c=column)
        installed += 1
finance_conn.commit()

print(f"  {installed} DBMS_RLS policies installed on FINANCE")
print(f"  masked columns: {', '.join(f'{t}.{c}' for t, c in MASKED_COLUMNS)}")
'''

CODE_DEMO = r'''# ---- 8.6  The proof: identical SQL, different answers -----------------------
# One statement, six personas. Nothing below filters rows or blanks columns in
# Python — the SELECT text never changes. Everything you see is the kernel
# applying the rules from 8.3, keyed on the end-user context set by
# AGENT.set_eda_ctx.

def set_persona(pid: str) -> None:
    with agent_conn.cursor() as cur:
        cur.execute("BEGIN AGENT.SET_EDA_CTX(:u); END;", u=end_user(pid))


def clear_persona() -> None:
    with agent_conn.cursor() as cur:
        cur.execute("BEGIN AGENT.SET_EDA_CTX(NULL, 'EXECUTIVE'); END;")


def measure() -> tuple:
    with agent_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(amount_cents) FROM FINANCE.TRANSACTIONS")
        tx_rows, amount_visible = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM FINANCE.SAR_REPORTS")
        sar_rows = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT region FROM FINANCE.TRANSACTIONS")
        short = {"AMERICAS": "AMER", "ASIA_PACIFIC": "APAC",
                 "EUROPE": "EU", "MIDDLE_EAST": "ME"}
        regions = sorted(short.get(r[0], r[0]) for r in cur)
    return tx_rows, regions, amount_visible, sar_rows


print(f"{'persona':<20} {'clearance':<10} {'tx rows':>8} {'regions':<20} "
      f"{'amount':>9} {'SAR':>5}")
print("-" * 78)
for pid, p in PERSONAS.items():
    set_persona(pid)
    tx_rows, regions, amount_visible, sar_rows = measure()
    amount = "visible" if amount_visible else "NULL"
    print(f"{pid:<20} {p['clearance']:<10} {tx_rows:>8} "
          f"{','.join(regions):<20} {amount:>9} {sar_rows:>5}")
clear_persona()

print("-" * 78)
print("The full table holds 1,199 transactions across 4 regions.")
print("'NULL' = the row came back, the value did not. A mask, not an absence.")
print("SAR reports are 0 for everyone except compliance.officer (default-deny).")
'''

CODE_WIRE = r'''# ---- 8.7  The handle the agent loop must not forget -------------------------
# Part 10's `tool_run_sql` sets the end-user context on every call, from this
# handle. One process-wide slot is enough for the notebook; the production app
# (app/backend/agent/tools.py) uses a thread/greenlet-local so two concurrent
# turns cannot borrow each other's identity.

CURRENT_END_USER = [None]          # None = no end user -> every predicate is 1=1


def act_as(pid: str) -> None:
    """Become a persona: set the handle and push it into the database session."""
    CURRENT_END_USER[0] = end_user(pid)
    set_persona(pid)


def act_as_nobody() -> None:
    """Drop back to 'no end user' — the fail-open state, useful to see the
    difference a context makes."""
    CURRENT_END_USER[0] = None
    clear_persona()


SQL = "SELECT txn_id, region, amount_cents FROM FINANCE.TRANSACTIONS"


def report(label: str) -> None:
    with agent_conn.cursor() as cur:
        cur.execute(SQL)
        rows = cur.fetchall()          # the whole result set, as the kernel allows it
    print(f"{label:<21}: {len(rows):>5} rows, "
          f"{len({r[1] for r in rows})} regions, "
          f"{sum(1 for r in rows if r[2] is not None):>5} with an amount")


act_as_nobody()
report("no context set")
act_as("analyst.east")
report("as analyst.east")
act_as_nobody()

print("\nSame SQL. The only thing that changed is who the session says it is.")
print("Part 10 applies this on every tool call; the app does the same in")
print("app/backend/agent/tools.py::tool_run_sql and api/data_routes.py.")
'''

MD_TARGET = r"""### The Deep Sec version, for when you run this on Enterprise

Everything above is the Free-edition stand-in. On a 26ai Enterprise-class database the
same registry compiles to data grants, and the rule set becomes declarative — the
database derives `NULL` columns from the grant itself rather than from a mask function:

```sql
CREATE DATA ROLE eda_analyst_east_role;
CREATE END USER "analyst.east@meridianbank.example" IDENTIFIED BY "...";
GRANT DATA ROLE eda_analyst_east_role TO "analyst.east@meridianbank.example";

-- rows: EU + ME only
CREATE OR REPLACE DATA GRANT eda_analyst_east_transactions AS
    SELECT ON FINANCE.TRANSACTIONS
    WHERE region IN ('EUROPE', 'MIDDLE_EAST')
    TO eda_analyst_east_role;

-- columns: this grant omits amount_cents, so it comes back NULL
CREATE OR REPLACE DATA GRANT eda_analyst_east_customers AS
    SELECT (customer_id, full_name, email) ON FINANCE.CUSTOMERS
    WHERE customer_id IN (...)
    TO eda_analyst_east_role;
```

The application then stops passing strings around and starts attaching an identity:

```python
ctx = oracledb.create_end_user_security_context(
    end_user_identity=("ANALYST.EAST@MERIDIANBANK.EXAMPLE", key),
    database_access_token=token,                 # OBO or client-credentials
    data_roles=["EDA_ANALYST_EAST_ROLE"],
)
conn.set_end_user_security_context(ctx)
```

And two functions let a query reason about its own permissions — useful because the app
can then render a proper mask instead of a blank cell, and can ask "may I?" before
attempting a write:

```sql
SELECT first_name, last_name,
       DECODE(ORA_IS_COLUMN_AUTHORIZED(ssn), FALSE, '000-00-00', TRUE, ssn) AS ssn
  FROM hr.employees;

SELECT ORA_CHECK_DATA_PRIVILEGE(emp, 'UPDATE', phone) AS can_update_phone
  FROM hr.employees emp;
```

**The workshop ships both paths.** `app/backend/db/deep_security.py` probes the database
on startup and drives whichever backend exists; `app/scripts/setup_deep_security.py`
installs the rule set and writes the real data-grant DDL to
`app/scripts/out/deep_sec_ddl.sql` for the day you point it at an Enterprise instance.
`api/identities.py` stays the single source of truth, so the dropdown, the SQL tool, the
Data Explorer and the kernel cannot drift apart.

> ### 💡 Key takeaways — Part 8
>
> - **Where the rule runs is the whole argument.** A rule applied in Python after the
>   fetch is not a boundary; the data already left the database.
> - **A mask naming a non-existent column fails silently in Python and loudly in SQL.**
>   This repo shipped one (`ACCOUNTS.ACCOUNT_NUMBER`); the kernel caught it instantly.
> - **Deep Sec is default-deny and kernel-enforced** — data grants, data roles,
>   end-user security context. It is an Enterprise-class 26ai feature.
> - **Free can still demonstrate the semantics** with an application context plus
>   `DBMS_RLS`, as long as you know it is fail-open without a context and that a
>   predicate may not subquery another policied table.
> - **Put the context on every read path.** The last two cells do that for `run_sql`;
>   forgetting it is how a kernel-enforced system silently reverts to an open one.
"""


def cell(kind, source, cid):
    c = {"cell_type": kind, "id": cid, "metadata": {},
         "source": source.splitlines(keepends=True)}
    if kind == "code":
        c["execution_count"] = None
        c["outputs"] = []
    return c


def main():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    src = ["".join(c["source"]) for c in nb["cells"]]
    anchor = next(i for i, s in enumerate(src)
                  if s.startswith("## Part 9 — Code execution"))

    # Idempotent: drop any previously generated Part 8 section first, so this
    # script can regenerate the section rather than only ever running once.
    existing = [i for i, s in enumerate(src) if s.startswith("## Part 8 —")]
    if existing:
        start = existing[0]
        removed = 0
        while start < len(nb["cells"]) and not "".join(
                nb["cells"][start]["source"]).startswith("## Part 9 — Code execution"):
            del nb["cells"][start]
            removed += 1
        print(f"removed {removed} existing Part 8 cell(s)")
        src = ["".join(c["source"]) for c in nb["cells"]]
        anchor = next(i for i, s in enumerate(src)
                      if s.startswith("## Part 9 — Code execution"))

    new = [
        cell("markdown", MD_INTRO, "p8-intro"),
        cell("markdown", MD_WHAT, "p8-what"),
        cell("code", CODE_PROBE, "p8-probe"),
        cell("code", CODE_REJECTED, "p8-rejected"),
        cell("markdown", MD_BACKENDS, "p8-backends"),
        cell("code", CODE_RULES, "p8-rules"),
        cell("code", CODE_INSTALL, "p8-install"),
        cell("code", CODE_POLICIES, "p8-policies"),
        cell("code", CODE_DEMO, "p8-demo"),
        cell("code", CODE_WIRE, "p8-wire"),
        cell("markdown", MD_TARGET, "p8-target"),
    ]
    nb["cells"][anchor:anchor] = new

    # Part 10's run_sql has to drive the context this section installed,
    # otherwise the agent's own SQL reads with no end user and every predicate
    # is 1=1. Patch it here so regeneration cannot lose the wiring.
    _wire_run_sql(nb)

    NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"inserted {len(new)} cells before cell {anchor} ({len(nb['cells'])} total)")


def _wire_run_sql(nb) -> None:
    """Idempotently make the notebook's tool_run_sql apply CURRENT_END_USER."""
    idx = next((i for i, c in enumerate(nb["cells"])
                if "def tool_run_sql" in "".join(c["source"])), None)
    if idx is None:
        print("warning: tool_run_sql not found; Part 10 wiring skipped")
        return
    src = "".join(nb["cells"][idx]["source"])
    if "AGENT.SET_EDA_CTX" in src:
        return                                  # already wired
    old = '''    if not _READ_ONLY.match(sql.strip()):
        return json.dumps({"error": "only SELECT / WITH statements are allowed in run_sql"})
    try:'''
    new = '''    if not _READ_ONLY.match(sql.strip()):
        return json.dumps({"error": "only SELECT / WITH statements are allowed in run_sql"})

    # Part 8: tell the database who this query is for, before it runs. The
    # kernel then decides which rows and columns come back — this function does
    # not filter anything. Remove these three lines and the query still
    # succeeds, but it returns every region unmasked: that is the difference
    # between a trust boundary and a post-fetch cleanup.
    if CURRENT_END_USER[0] is not None:
        with agent_conn.cursor() as cur:
            cur.execute("BEGIN AGENT.SET_EDA_CTX(:u); END;", u=CURRENT_END_USER[0])

    try:'''
    if old not in src:
        print("warning: tool_run_sql shape changed; Part 10 wiring skipped")
        return
    nb["cells"][idx]["source"] = src.replace(old, new).splitlines(keepends=True)
    print(f"wired tool_run_sql (cell {idx}) to CURRENT_END_USER")


if __name__ == "__main__":
    main()
