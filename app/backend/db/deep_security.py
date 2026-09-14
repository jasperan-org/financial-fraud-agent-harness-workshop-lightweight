"""Identity-aware data access — one persona registry, two enforcement backends.

The workshop's `api/identities.py` registry defines the personas (analyst, CFO,
compliance officer, ...) and their row/column rules. Historically those rules
were enforced **only** in Python: `api/data_routes.py` and
`agent/tools.py::tool_run_sql` dropped rows and redacted columns *after* the
database had already returned them. `scripts/setup_advanced.py` did install two
`DBMS_RLS` policies, but nothing in the request path ever called
`AGENT.SET_EDA_CTX`, so `SYS_CONTEXT('EDA_CTX','END_USER')` was always NULL and
the policies evaluated to `1=1` — the kernel layer was inert.

This module closes that gap and makes the enforcement boundary explicit. It
detects what the connected database can actually do and drives the strongest
available backend:

    DEEP_SEC   26ai Enterprise-class (Base DB / Exadata / Autonomous AI
               Database). The real feature: `CREATE DATA ROLE`,
               `CREATE DATA GRANT`, `CREATE END USER`, `CREATE APPLICATION
               IDENTITY`, plus an `EndUserSecurityContext` payload from the
               client driver. Authorization lives entirely in the kernel.

    VPD        Oracle AI Database 26ai **Free** and older releases. Row
               predicates, column masks and table denials are installed as
               `DBMS_RLS` policies driven by the `EDA_CTX` application context.
               Same semantics, different mechanism — this is what the shipped
               Codespace actually runs.

    APP_ONLY   Nothing installed at the database layer; only the Python
               post-filters in `api/identities.py` apply. The demo still works
               but the trust boundary is the application, which is exactly the
               failure mode the notebook's Part 8 argues against.

Note on the Free edition: `DBMS_DEEP_SEC` is absent, every Deep Sec dictionary
view is absent, and `CREATE DATA ROLE` / `CREATE END USER` / `CREATE DATA GRANT`
/ `CREATE DATA SECURITY POLICY` all fail with `ORA-00901 (invalid CREATE
command)`. `probe()` reports that honestly instead of failing at demo time.

The persona → end-user-name convention matches what `setup_advanced.py` already
seeds: ``<persona id>@meridianbank.example``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

# Persona ids map to end-user names the same way `agent_authorizations` is
# already seeded, so the DB layer and the UI dropdown agree on one identity.
END_USER_DOMAIN = "meridianbank.example"

# `oracledb.create_end_user_security_context()` landed in python-oracledb 4.0.
MIN_DRIVER_FOR_DEEP_SEC = (4, 0)

DEEP_SEC = "DEEP_SEC"
VPD = "VPD"
APP_ONLY = "APP_ONLY"


def end_user_name(identity_id: str) -> str:
    """`analyst.east` -> `analyst.east@meridianbank.example`."""
    return f"{identity_id}@{END_USER_DOMAIN}"


def identifier_fragment(identity_id: str) -> str:
    """`analyst.east` -> `ANALYST_EAST` (legal inside an unquoted identifier)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", identity_id).strip("_").upper()


def data_role_name(identity_id: str) -> str:
    """`analyst.east` -> `EDA_ANALYST_EAST_ROLE`."""
    return f"EDA_{identifier_fragment(identity_id)}_ROLE"


# --------------------------------------------------------------------------- #
# Capability probe
# --------------------------------------------------------------------------- #


@dataclass
class Capability:
    """What the connected database can actually enforce."""

    backend: str = APP_ONLY
    version: str = "unknown"
    edition: str = "unknown"
    has_dbms_deep_sec: bool = False
    has_data_grant_views: bool = False
    has_dbms_rls: bool = False
    has_eda_context: bool = False
    has_eda_setter: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def supports_deep_sec(self) -> bool:
        return self.has_dbms_deep_sec and self.has_data_grant_views

    @property
    def supports_vpd(self) -> bool:
        return self.has_dbms_rls

    def summary(self) -> str:
        return (
            f"backend={self.backend} version={self.version!r} "
            f"deep_sec={self.supports_deep_sec} vpd={self.supports_vpd} "
            f"eda_context={self.has_eda_context}"
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "version": self.version,
            "edition": self.edition,
            "deep_sec": self.supports_deep_sec,
            "vpd": self.supports_vpd,
            "eda_context": self.has_eda_context,
            "notes": list(self.notes),
        }


def _edition_of(banner: str) -> str:
    """Classify the v$version banner. Free/EE/SE is what changes capability."""
    upper = banner.upper()
    for needle, label in (
        ("FREE", "FREE"),
        ("ENTERPRISE", "ENTERPRISE"),
        ("STANDARD", "STANDARD"),
        ("PERSONAL", "PERSONAL"),
    ):
        if needle in upper:
            return label
    return "unknown"


def _scalar(cur, sql: str, default=None, **binds):
    """Run a probe query, tolerating views that this edition does not have."""
    try:
        cur.execute(sql, binds or None)
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


# Probing costs six dictionary queries and the answer cannot change while the
# process lives, so it is done once per process. `refresh=True` re-reads it
# (used after an installer run).
_CAPABILITY_CACHE: "Capability | None" = None


def probe(conn, *, refresh: bool = False) -> Capability:
    """Inspect the connected database and decide which backend can be driven.

    Every check is a dictionary query, so this is safe to run on any edition and
    safe to run as a low-privilege user. Cached after the first call.
    """
    global _CAPABILITY_CACHE
    if _CAPABILITY_CACHE is not None and not refresh:
        return _CAPABILITY_CACHE
    cap = _probe_uncached(conn)
    _CAPABILITY_CACHE = cap
    return cap


def _probe_uncached(conn) -> Capability:
    cap = Capability()
    with conn.cursor() as cur:
        cap.version = str(
            _scalar(cur, "SELECT banner_full FROM v$version", "unknown")
        ).splitlines()[0]

        cap.edition = _edition_of(cap.version)

        cap.has_dbms_deep_sec = bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM all_objects "
                " WHERE object_name LIKE 'DBMS_DEEP_SEC%'",
                0,
            )
        )
        cap.has_data_grant_views = bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM all_views WHERE view_name IN "
                " ('DBA_DATA_GRANTS','ALL_DATA_GRANTS','DBA_DATA_ROLES',"
                "  'DBA_END_USERS','DBA_APPLICATION_IDENTITIES')",
                0,
            )
        )
        cap.has_dbms_rls = bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM all_objects WHERE object_name LIKE 'DBMS_RLS%'",
                0,
            )
        )
        cap.has_eda_context = bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM all_context WHERE namespace = 'EDA_CTX'",
                0,
            )
        ) or bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM dba_context WHERE namespace = 'EDA_CTX'",
                0,
            )
        )
        cap.has_eda_setter = bool(
            _scalar(
                cur,
                "SELECT COUNT(*) FROM all_objects "
                " WHERE object_name = 'SET_EDA_CTX' AND object_type = 'PROCEDURE'",
                0,
            )
        )

    if cap.supports_deep_sec:
        cap.backend = DEEP_SEC
    elif cap.supports_vpd:
        cap.backend = VPD
        if not (cap.has_eda_context and cap.has_eda_setter):
            cap.notes.append(
                "DBMS_RLS is available but the EDA_CTX namespace/setter is not "
                "installed yet — run scripts/setup_deep_security.py to install it."
            )
        if "Free" in cap.version or "Free" in cap.edition:
            cap.notes.append(
                "Oracle AI Database Free: DBMS_DEEP_SEC and the Deep Sec DDL "
                "(CREATE DATA ROLE / DATA GRANT / END USER) are not present, so "
                "the VPD backend is the strongest available enforcement."
            )
    else:
        cap.backend = APP_ONLY
        cap.notes.append(
            "Neither Deep Sec nor DBMS_RLS is available; only the Python "
            "post-filters in api/identities.py apply."
        )
    return cap


# --------------------------------------------------------------------------- #
# Persona -> policy matrix
# --------------------------------------------------------------------------- #

# Which tables carry an identity-relevant `REGION`, directly or via a join.
# Mirrors `api.identities.region_filter_clause` exactly so the kernel and the
# application agree row-for-row.
REGION_EXPR: dict[str, str] = {
    "TRANSACTIONS": "region",
    "BRANCHES": "region",
    "MERCHANTS": "region",
    "ACCOUNTS": (
        "branch_id IN (SELECT branch_id FROM FINANCE.branches "
        "             WHERE region IN ({regions}))"
    ),
    "LOANS": (
        "branch_id IN (SELECT branch_id FROM FINANCE.branches "
        "             WHERE region IN ({regions}))"
    ),
    "CARDS": (
        "account_id IN (SELECT a.account_id FROM FINANCE.accounts a "
        "                 JOIN FINANCE.branches b ON b.branch_id = a.branch_id "
        "                WHERE b.region IN ({regions}))"
    ),
    "CUSTOMERS": (
        "customer_id IN (SELECT a.customer_id FROM FINANCE.accounts a "
        "                  JOIN FINANCE.branches b ON b.branch_id = a.branch_id "
        "                 WHERE b.region IN ({regions}))"
    ),
    "SAR_REPORTS": (
        "customer_id IN (SELECT a.customer_id FROM FINANCE.accounts a "
        "                  JOIN FINANCE.branches b ON b.branch_id = a.branch_id "
        "                 WHERE b.region IN ({regions}))"
    ),
}


def policy_matrix(identities: dict) -> list[dict[str, Any]]:
    """Flatten the persona registry into an explicit, inspectable rule list.

    Each row is one rule the database must enforce:

        {"persona": "analyst.east", "kind": "row",    "table": "TRANSACTIONS", ...}
        {"persona": "agent",        "kind": "column", "table": "CUSTOMERS", "column": "SSN"}
        {"persona": "ops.viewer",   "kind": "deny",   "table": "CUSTOMERS"}
    """
    rules: list[dict[str, Any]] = []
    for ident in identities.values():
        for table in REGION_EXPR:
            rules.append({
                "persona": ident.id,
                "end_user": end_user_name(ident.id),
                "kind": "row",
                "owner": "FINANCE",
                "table": table,
                "regions": list(ident.regions) if ident.regions else ["ALL"],
            })
        for qualified in ident.mask_cols:
            owner, table, column = _split_column(qualified)
            rules.append({
                "persona": ident.id,
                "end_user": end_user_name(ident.id),
                "kind": "column",
                "owner": owner,
                "table": table,
                "column": column,
            })
        for qualified in ident.forbid_tables:
            owner, table = qualified.split(".", 1)
            rules.append({
                "persona": ident.id,
                "end_user": end_user_name(ident.id),
                "kind": "deny",
                "owner": owner,
                "table": table,
            })
    return rules


def _split_column(qualified: str) -> tuple[str, str, str]:
    parts = qualified.split(".")
    if len(parts) != 3:
        raise ValueError(f"expected SCHEMA.TABLE.COLUMN, got {qualified!r}")
    return parts[0].upper(), parts[1].upper(), parts[2].upper()


# --------------------------------------------------------------------------- #
# Backend A: Deep Data Security (26ai Enterprise / Autonomous)
# --------------------------------------------------------------------------- #


def deep_sec_ddl(
    identities: dict,
    table_columns: dict[str, list[str]],
    *,
    end_user_password: str | None = None,
    application_identity: str | None = None,
) -> list[str]:
    """Generate the Deep Data Security DDL that expresses the persona registry.

    This is the *target* form for a 26ai Enterprise-class database. It is
    generated (not executed) whenever the connected database does not expose
    Deep Sec, which is the case on the Free edition. Returns ready-to-run
    statements in dependency order.

    `table_columns` maps ``"FINANCE.TRANSACTIONS"`` to its column names in
    dictionary order; masked columns are simply left out of the SELECT grant,
    which is how Deep Sec returns them as NULL.
    """
    stmts: list[str] = [
        "-- =====================================================================",
        "-- Oracle Deep Data Security (26ai) — generated from api/identities.py",
        "-- Requires: Oracle AI Database 26ai Enterprise-class (Base DB, Exadata,",
        "--           Autonomous AI Database). Not available on the Free edition.",
        "-- =====================================================================",
    ]

    if application_identity:
        stmts.append(
            f"CREATE APPLICATION IDENTITY {application_identity} "
            f"MAPPED TO 'OCI_CLIENT=<agent-oauth-client-id>';"
        )

    for ident in identities.values():
        role = data_role_name(ident.id)
        user = end_user_name(ident.id)
        stmts.append("")
        stmts.append(f"-- persona: {ident.id}  ({ident.label}, {ident.clearance})")
        stmts.append(f"CREATE DATA ROLE {role};")

        if end_user_password:
            # End users are UPNs, so the identifier is quoted to survive the '@'.
            stmts.append(
                f'CREATE END USER "{user}" IDENTIFIED BY "{end_user_password}";'
            )
        stmts.append(f'GRANT DATA ROLE {role} TO "{user}";')
        if application_identity:
            stmts.append(f"GRANT DATA ROLE {role} TO {application_identity};")

        regions = ident.regions or ["ALL"]
        if ident.regions:
            region_list = ", ".join(f"'{r}'" for r in sorted(ident.regions))
        else:
            region_list = None

        forbidden = {q.upper() for q in ident.forbid_tables}

        for table, expr in REGION_EXPR.items():
            qualified = f"FINANCE.{table}"
            if qualified.upper() in forbidden:
                # Default-deny is expressed by NOT issuing a grant. Emitting one
                # here would quietly hand SAR_REPORTS to every analyst.
                continue
            cols = table_columns.get(qualified)
            if region_list is None:
                # ALL regions: a row grant with no predicate.
                predicate = None
            else:
                predicate = expr.format(regions=region_list)

            masked = {
                column
                for owner, tbl, column in (_split_column(m) for m in ident.mask_cols)
                if f"{owner}.{tbl}" == qualified
            }
            granted = [c for c in (cols or []) if c not in masked]

            grant_name = f"EDA_{identifier_fragment(ident.id)}_{table}"
            head = (
                f"CREATE OR REPLACE DATA GRANT {grant_name} AS\n"
                f"    SELECT{_column_list(granted)}\n"
                f"    ON {qualified}"
            )
            if predicate:
                head += f"\n    WHERE {predicate}"
            stmts.append(head + f"\n    TO {role};")

        for qualified_table in ident.forbid_tables:
            owner, table = qualified_table.split(".", 1)
            # No grant at all is the deny: Deep Sec is default-deny, so the
            # absence of a data grant is what keeps SAR_REPORTS out of reach.
            stmts.append(
                f"-- deny: no data grant is issued for {owner}.{table} "
                f"to {role} (default-deny)"
            )
    stmts += [
        "",
        "-- Runtime: the application attaches an EndUserSecurityContext per request.",
        "--   import oracledb",
        "--   ctx = oracledb.create_end_user_security_context(",
        "--       end_user_identity=(\"ANALYST.EAST@MERIDIANBANK.EXAMPLE\", key),",
        "--       database_access_token=token,          # OBO or client-credentials",
        "--       data_roles=[\"EDA_ANALYST_EAST_ROLE\"],",
        "--   )",
        "--   conn.set_end_user_security_context(ctx)",
        "-- Query-side helpers: ORA_IS_COLUMN_AUTHORIZED(col) distinguishes a real",
        "-- NULL from a masked one; ORA_CHECK_DATA_PRIVILEGE(obj,'UPDATE',col)",
        "-- answers 'may I?' before the statement runs.",
    ]
    return stmts


def _column_list(columns: Sequence[str]) -> str:
    """`(A, B, C)` or empty string when every column is authorized."""
    if not columns:
        return ""
    return " (" + ", ".join(columns) + ")"


def latest_driver_supports_deep_sec() -> tuple[bool, str]:
    """Whether the installed python-oracledb can send an EndUserSecurityContext."""
    try:
        import oracledb  # noqa: PLC0415 - optional at import time
    except Exception as exc:  # pragma: no cover - driver always present in the app
        return False, f"python-oracledb not importable: {exc}"

    version = tuple(int(p) for p in oracledb.__version__.split(".")[:2])
    if version < MIN_DRIVER_FOR_DEEP_SEC:
        return False, (
            f"python-oracledb {oracledb.__version__} cannot attach an "
            f"EndUserSecurityContext; need >= "
            f"{'.'.join(str(p) for p in MIN_DRIVER_FOR_DEEP_SEC)}"
        )
    if not hasattr(oracledb, "create_end_user_security_context"):
        return False, (
            f"python-oracledb {oracledb.__version__} has no "
            f"create_end_user_security_context()"
        )
    return True, f"python-oracledb {oracledb.__version__}"


# --------------------------------------------------------------------------- #
# Backend B: VPD + application context (works on 26ai Free)
# --------------------------------------------------------------------------- #

def vpd_seed(identities: dict) -> dict[str, list[tuple]]:
    """Rows to seed into the three policy tables, derived from the registry."""
    auth: list[tuple] = []
    masks: list[tuple] = []
    denials: list[tuple] = []
    clearances: list[tuple] = []

    for ident in identities.values():
        user = end_user_name(ident.id)
        clearances.append((user, ident.clearance, ident.description[:400]))
        for region in (ident.regions or ["ALL"]):
            auth.append((user, region))
        for qualified in ident.mask_cols:
            owner, table, column = _split_column(qualified)
            masks.append((user, owner, table, column))
        for qualified in ident.forbid_tables:
            owner, table = qualified.split(".", 1)
            denials.append((user, owner.upper(), table.upper()))

    return {"authorizations": auth, "masks": masks, "denials": denials,
            "clearances": clearances}


def set_identity(conn, identity, *, end_user: str | None = None) -> str:
    """Push the acting persona into the database session, kernel-side.

    VPD backend: calls the trusted setter `AGENT.SET_EDA_CTX`, which is the only
    procedure allowed to write the `EDA_CTX` namespace. Every `DBMS_RLS`
    predicate on FINANCE then evaluates against this value.

    Deep Sec backend: the identity travels as an `EndUserSecurityContext`
    payload; that path needs an IAM-issued database-access token, so it raises
    with the exact requirement rather than silently degrading.

    Returns the backend that was actually driven.
    """
    user = end_user or end_user_name(identity.id)
    cap = probe(conn)

    if cap.backend == DEEP_SEC:
        ok, detail = latest_driver_supports_deep_sec()
        if not ok:
            raise RuntimeError(f"Deep Sec present but client cannot use it: {detail}")
        raise RuntimeError(
            "Deep Sec requires an IAM-issued database-access token per request. "
            "Wire oracledb.create_end_user_security_context(end_user_identity=..., "
            "database_access_token=..., data_roles=[...]) into the connection "
            "factory, then call conn.set_end_user_security_context(ctx)."
        )

    if cap.backend == VPD:
        with conn.cursor() as cur:
            # Trailing slash-free anonymous block; the setter looks the
            # clearance up from AGENT.agent_clearances.
            cur.execute("BEGIN AGENT.SET_EDA_CTX(:u); END;", u=user)
        return VPD

    return APP_ONLY


def clear_identity(conn) -> None:
    """Reset the session to 'no end user' so policies evaluate to 1=1."""
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN AGENT.SET_EDA_CTX(NULL, 'EXECUTIVE'); END;")
    except Exception:
        pass


def visible_rows(conn, table: str = "FINANCE.TRANSACTIONS") -> int:
    """Row count as the *current* session context sees it."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


def column_is_null_for(conn, table: str, column: str) -> tuple[int, int]:
    """(#rows, #non-null values) for one column — proves a mask is live."""
    owner, tbl = table.split(".", 1)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*), COUNT({owner}.{tbl}.{column}) FROM {table}"
        )
        return cur.fetchone()
