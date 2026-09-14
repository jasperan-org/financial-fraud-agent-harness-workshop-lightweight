# Part 8: Identity-Aware Data Access — from Python filters to the kernel

> **Oracle documentation:** [`Oracle Deep Data Security Guide, 26ai`](https://docs.oracle.com/en/database/oracle/oracle-database/26/ddscg/index.html)
> · [`Deep Data Security product page`](https://www.oracle.com/security/database-security/features/deep-data-security/)

> 🧭 **Advanced reference.** Not one of the five core TODOs in the 90-minute path. The rule set is seeded by `app/scripts/setup_deep_security.py`, the running app drives it on every read, and the reference notebook
> [`enterprise_data_agent.ipynb`](../enterprise_data_agent.ipynb) implements it end to end as **Part 8**.

Parts 4–7 give the agent memory. Part 8 asks a different question: **what is the agent allowed to see, and who decides?**

The harness has personas — the `Use As:` dropdown in the app, defined in
[`app/backend/api/identities.py`](../app/backend/api/identities.py). Each carries a clearance,
authorized regions, columns to redact, and tables to refuse. The interesting part is not *which*
rules exist. It is **where they run**.

## The problem: a filter is not a boundary

If the rules live in Python, the database has already handed over the rows by the time they apply.
The agent asks for `SELECT * FROM FINANCE.TRANSACTIONS`, Oracle returns all four regions, and a
`for` loop in Flask throws some away. That is a UI preference with a security-shaped comment above
it, and it holds only until someone finds a path around the loop.

### The bug that proves it

This repository's own persona registry shipped this rule:

```python
_ACCOUNT_IDENTIFIER_MASKS = ["FINANCE.ACCOUNTS.ACCOUNT_NUMBER", ...]
```

`FINANCE.ACCOUNTS` has **no `ACCOUNT_NUMBER` column**. It never did — the account key is the
numeric `ACCOUNT_ID`, and the sensitive value on that table is `BALANCE_CENTS`. In Python the rule
failed silently, because a mask naming a nonexistent column is indistinguishable from a mask that
works. The moment the same rule is pushed into the database, Oracle rejects it:

```
ORA-23607: invalid column "ACCOUNT_NUMBER"
```

That is the whole argument for this part. A rule the kernel cannot compile is a rule you learn about
immediately. A rule the application "applies" is a rule you learn about in the incident review.

## What Oracle Deep Data Security is

Oracle **Deep Data Security** ("Deep Sec") is the database-native authorization model introduced in
**Oracle AI Database 26ai** for exactly this situation: agents and applications querying on behalf of
an end user.

| Concept | Statement | What it does |
|---|---|---|
| **Data grant** | `CREATE DATA GRANT` | Authorizes `SELECT/UPDATE/INSERT/DELETE` on an object, optionally narrowed by a `WHERE` predicate and a column list. Additive, and **default-deny**. |
| **Data role** | `CREATE DATA ROLE` | Maps to a role in external IAM (OCI IAM, Entra ID) or is managed locally in the database. |
| **End user** | `CREATE END USER` | An application user that owns no schema. These are the workshop's personas. |
| **Application identity** | `CREATE APPLICATION IDENTITY` | The agent or app itself, mapped to its OAuth client identifier. |
| **End-user security context** | driver-attached payload | Carries the acting identity per request. |
| **Access-check functions** | `ORA_IS_COLUMN_AUTHORIZED`, `ORA_CHECK_DATA_PRIVILEGE` | Let a query reason about its own permissions. |

Example — an analyst scoped to two regions, with amounts withheld:

```sql
CREATE DATA ROLE eda_analyst_east_role;
CREATE END USER "analyst.east@meridianbank.example" IDENTIFIED BY "...";
GRANT DATA ROLE eda_analyst_east_role TO "analyst.east@meridianbank.example";

-- rows: EUROPE + MIDDLE_EAST only
CREATE OR REPLACE DATA GRANT eda_analyst_east_transactions AS
    SELECT ON FINANCE.TRANSACTIONS
    WHERE region IN ('EUROPE', 'MIDDLE_EAST')
    TO eda_analyst_east_role;

-- columns: this grant omits amount_cents, so it is returned as NULL
CREATE OR REPLACE DATA GRANT eda_analyst_east_customers AS
    SELECT (customer_id, full_name, email) ON FINANCE.CUSTOMERS
    WHERE customer_id IN (...)
    TO eda_analyst_east_role;
```

The client then attaches an identity instead of trusting itself:

```python
ctx = oracledb.create_end_user_security_context(
    end_user_identity=("ANALYST.EAST@MERIDIANBANK.EXAMPLE", key),
    database_access_token=token,                 # OBO or client-credentials
    data_roles=["EDA_ANALYST_EAST_ROLE"],
)
conn.set_end_user_security_context(ctx)
```

The agent no longer has to be trusted. It can emit the broadest SQL it likes; the kernel returns the
rows its end user is entitled to and nothing else.

## What this exercise database can actually do

Deep Sec is an **Enterprise-class** feature. The workshop runs **Oracle AI Database 26ai Free** in a
container, where it is absent. Measured on the live database:

```
release            : Oracle AI Database 26ai Free Release 23.26.1.0.0
DBMS_DEEP_SEC      : ABSENT
data-grant views   : ABSENT        (no DBA_DATA_GRANTS / DBA_DATA_ROLES / DBA_END_USERS)
DBMS_RLS           : present
=> enforcement     : VPD
```

and every Deep Sec DDL form is rejected with `ORA-00901 (invalid CREATE command)`:

| Statement | Result on 26ai Free |
|---|---|
| `CREATE DATA ROLE eda_probe_role` | `ORA-00901` |
| `CREATE END USER eda_probe_user` | `ORA-00901` |
| `CREATE DATA GRANT ... AS SELECT ...` | `ORA-00901` |
| `CREATE DATA SECURITY POLICY ... USING (1=1)` | `ORA-00901` |

Note the last row: even the earlier `CREATE DATA SECURITY POLICY` form is unavailable, so the
declarative branch in `app/scripts/setup_advanced.py` **always** falls through to its `DBMS_RLS`
fallback on this image.

## Two backends, one rule set

`app/backend/db/deep_security.py` probes the database and drives the strongest available backend.
`api/identities.py` stays the single source of truth, so the dropdown, the SQL tool, the Data
Explorer and the kernel cannot drift apart.

| | `DEEP_SEC` | `VPD` (this repo, on Free) | `APP_ONLY` |
|---|---|---|---|
| **Requires** | 26ai Enterprise-class (Base DB, Exadata, Autonomous AI Database) + IAM tokens | 26ai Free and older, `DBMS_RLS` | nothing |
| **Rows** | `CREATE DATA GRANT ... WHERE <predicate>` | `DBMS_RLS.ADD_POLICY` + application context | Python drops rows after fetch |
| **Columns** | omitted columns return `NULL` | `sec_relevant_cols` + `ALL_ROWS` returns `NULL` | Python overwrites with `[REDACTED]` |
| **Default** | default-deny | **fail-open** without a context | fail-open |
| **Trust boundary** | the kernel | the kernel | the application |

### How the VPD backend is wired

```
AGENT.agent_authorizations   end_user -> auth_region          (ALL means every region)
AGENT.agent_clearances       end_user -> clearance
AGENT.agent_masks            end_user -> owner.table.column   (columns to blank)
AGENT.agent_denials          end_user -> owner.table          (tables to refuse)
AGENT.agent_scope            end_user -> branch/account/customer keys (precomputed)
        |
        v
AGENT.set_eda_ctx(:end_user)   the ONLY writer of the EDA_CTX namespace
        |
        v
EDA_REGION_PREDICATE   EDA_SCOPE_PREDICATE   EDA_DENY_PREDICATE   EDA_MASK_<table>_<col>
        |
        v
15 DBMS_RLS policies on FINANCE
```

Three lessons are baked into that shape:

1. **The context setter is trusted.** Only `AGENT.set_eda_ctx` may write `EDA_CTX`, so a caller
   cannot simply declare itself the CFO. It derives clearance from `agent_clearances`.
2. **A predicate may not subquery another policied table.** Nesting `SELECT ... FROM
   FINANCE.branches` inside a policy on `FINANCE.accounts` raises `ORA-28113` at query time, because
   `branches` carries its own policy. Hence `agent_scope`: the reachable keys are precomputed and the
   predicate is a plain `EXISTS` against an unprotected table.
3. **Each masked column needs its own predicate function.** `DBMS_RLS` binds `sec_relevant_cols`
   into the *policy*, not into the function signature, so the function cannot see which column
   triggered it.

## Prove it

```bash
cd app && python scripts/setup_deep_security.py --demo
```

```
persona              clearance  transactions regions          amount  SAR rows   balance
--------------------------------------------------------------------------------------------
agent                STANDARD           1199 AMER,APAC,EU,ME     NULL         0      NULL
cfo                  EXECUTIVE          1199 AMER,APAC,EU,ME  visible         0   visible
compliance.officer   EXECUTIVE          1199 AMER,APAC,EU,ME  visible        15   visible
analyst.east         STANDARD            553 EU,ME               NULL         0      NULL
analyst.west         STANDARD            646 AMER,APAC           NULL         0      NULL
ops.viewer           STANDARD           1199 AMER,APAC,EU,ME     NULL         0      NULL
```

One `SELECT`, six personas, no application-layer filtering anywhere on the path. `NULL` means
*masked*, not empty: the row came back, the value did not.

The full matrix — every table × every persona — with an independent check:

| persona | transactions | branches | merchants | accounts | loans | cards | customers | SAR |
|---|---|---|---|---|---|---|---|---|
| agent | 1199 | 25 | 40 | 250 | 60 | 286 | 200 | 0 |
| cfo | 1199 | 25 | 40 | 250 | 60 | 286 | 200 | 0 |
| compliance.officer | 1199 | 25 | 40 | 250 | 60 | 286 | 200 | **15** |
| analyst.east | 553 | 11 | 16 | 120 | 31 | 139 | 111 | 0 |
| analyst.west | 646 | 14 | 24 | 130 | 29 | 147 | 114 | 0 |
| ops.viewer | 1199 | 25 | 40 | 250 | 60 | 286 | **0** | 0 |

## Where it is wired into the app

The kernel layer only matters if every read path drives it. `AGENT.SET_EDA_CTX` was previously
referenced *only* by the installer, which meant `SYS_CONTEXT('EDA_CTX','END_USER')` was always `NULL`
during real requests and the installed policies evaluated to `1=1`. Both read paths now set the
context before executing:

- [`app/backend/agent/tools.py`](../app/backend/agent/tools.py) — `tool_run_sql`, so SQL the model
  composes is gated by the kernel
- [`app/backend/api/data_routes.py`](../app/backend/api/data_routes.py) — the Data Explorer's rows
  endpoint

The Python post-filters stay in place as defence in depth and become no-ops when the database has
already answered correctly.

In the reference notebook the same wiring lives in **Part 10** (`tool_run_sql`), driven by the
`CURRENT_END_USER` handle this part defines. `act_as("analyst.east")` sets that handle *and* pushes
the context into the session, so the notebook's agent loop inherits the boundary without knowing it
exists. Regenerate the section from the repository root with
`python scripts/insert_part8_section.py` — it is idempotent and re-applies the Part 10 wiring.

> ⚠️ **Two honest caveats.**
> 1. **The VPD path is fail-open.** With no context set, every predicate evaluates to `1=1` and all
>    rows are visible. Deep Sec is default-deny. That is the single biggest behavioural difference
>    between what this repo demonstrates and what the feature provides.
> 2. **The app shares one connection across turns.** Setting a session context on a shared connection
>    is safe only because each read sets it immediately before executing. A production harness would
>    use one connection (or a session pool with fixed contexts) per concurrent turn.

## Running it on a database that has Deep Sec

```bash
cd app && python scripts/setup_deep_security.py --ddl-only
```

This writes `app/scripts/out/deep_sec_ddl.sql` — 67 statements generated from the same persona
registry: 6 data roles, 6 quoted end users, 12 role grants (end user + application identity), 42 row
and column data grants, and the application identity itself. Reviewed by hand, that file is the
migration.

> **Verification status.** The generated Deep Sec DDL is produced from the live schema but has **not**
> been executed, because no 26ai Enterprise-class instance is available to this repo. Everything in the
> `VPD` column of the tables above was executed and verified against the live container.

## The file that generates this section

Part 8 of the notebook is generated, not hand-edited:

```bash
python scripts/insert_part8_section.py    # idempotent; replaces Part 8 and re-wires Part 10
python scripts/build_student_notebook.py  # validates every checked-in notebook still parses
```

The generator holds the source of truth for the section's code cells. Editing the notebook directly
works until the next regeneration, and the same applies to the Part 10 wiring — which is exactly the
trap this section fell into once, when a quoting fix applied to the notebook was silently reverted by
a rebuild.

## Checklist for a real deployment

1. Run `setup_deep_security.py --ddl-only` and review `deep_sec_ddl.sql`.
2. Register the database as an OAuth resource in OCI IAM or Entra ID; register the agent as an OAuth
   client with a client-credentials grant.
3. Execute the DDL on the target; adjust end-user names to your IAM principal identifiers (UPNs).
4. Replace the `VPD` backend in `db/deep_security.py::set_identity` by attaching an
   `EndUserSecurityContext` per request. The persona-to-data-role mapping is already there.
5. Add an audit of which sessions set a context, then remove the Python post-filters — they should be
   redundant.
6. Prefer `ORA_IS_COLUMN_AUTHORIZED` over a blank cell in the UI, so a masked value renders as a
   deliberate mask rather than an empty field.
