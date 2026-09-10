"""Bank / AML schema + spatial setup + seed data + JSON duality views.

Mirrors the notebook's Part 5.4 + Part 11.6 cells, condensed into a single
re-runnable function. Idempotent: re-running drops and re-creates objects with
the same content.

The world is "Meridian Bank": 25 branches with SDO_GEOMETRY locations across
four regions (AMERICAS, EUROPE, MIDDLE_EAST, ASIA_PACIFIC), ~200 customers,
~250 accounts, ~300 cards, ~40 merchants, ~1,200 transactions over the last
90 days (including deliberate AML patterns: structuring, geographic velocity,
high-risk-corridor wires, rapid cash-out, large cash deposits), 60 loans and
15 Suspicious Activity Reports (SAR_REPORTS — the compliance-only table that
drives the Part 8 identity demo).
"""

from __future__ import annotations

import datetime as _dt
import random

import oracledb


SCHEMA = "FINANCE"

REGIONS = ["AMERICAS", "EUROPE", "MIDDLE_EAST", "ASIA_PACIFIC"]

# Flag reasons the AML rules write onto transactions (used by the agent's
# "which transactions were flagged and why" material).
FLAG_REASONS = [
    "STRUCTURING",
    "GEO_VELOCITY",
    "HIGH_RISK_COUNTRY",
    "RAPID_CASH_OUT",
    "LARGE_CASH_DEPOSIT",
]


# ---------- DDL --------------------------------------------------------------
DDL = [
    """CREATE TABLE branches (
         branch_id      NUMBER(10) PRIMARY KEY,
         branch_code    VARCHAR2(8) UNIQUE NOT NULL,
         name           VARCHAR2(120) NOT NULL,
         city           VARCHAR2(60),
         country        VARCHAR2(60),
         region         VARCHAR2(20) NOT NULL,
         latitude       NUMBER(10,6),
         longitude      NUMBER(10,6),
         location       SDO_GEOMETRY,
         opened_year    NUMBER(4)
       )""",
    """CREATE TABLE customers (
         customer_id    NUMBER(10) PRIMARY KEY,
         full_name      VARCHAR2(120) NOT NULL,
         ssn            VARCHAR2(11) UNIQUE NOT NULL,
         country        VARCHAR2(60),
         segment        VARCHAR2(20) NOT NULL,
         risk_rating    NUMBER(3)
       )""",
    """CREATE TABLE accounts (
         account_id     NUMBER(10) PRIMARY KEY,
         customer_id    NUMBER(10) NOT NULL REFERENCES customers(customer_id),
         branch_id      NUMBER(10) NOT NULL REFERENCES branches(branch_id),
         account_type   VARCHAR2(20) NOT NULL,
         currency       VARCHAR2(3) NOT NULL,
         balance_cents  NUMBER(15),
         opened_ts      TIMESTAMP,
         status         VARCHAR2(20) NOT NULL
       )""",
    """CREATE TABLE cards (
         card_id        NUMBER(10) PRIMARY KEY,
         account_id     NUMBER(10) NOT NULL REFERENCES accounts(account_id),
         card_type      VARCHAR2(20) NOT NULL,
         card_number    VARCHAR2(16) UNIQUE NOT NULL,
         issued_ts      TIMESTAMP,
         status         VARCHAR2(20) NOT NULL,
         daily_limit_cents NUMBER(15)
       )""",
    """CREATE TABLE merchants (
         merchant_id    NUMBER(10) PRIMARY KEY,
         name           VARCHAR2(120) NOT NULL,
         mcc_code       VARCHAR2(4),
         category       VARCHAR2(60),
         country        VARCHAR2(60),
         region         VARCHAR2(20) NOT NULL,
         latitude       NUMBER(10,6),
         longitude      NUMBER(10,6),
         location       SDO_GEOMETRY
       )""",
    """CREATE TABLE transactions (
         txn_id         NUMBER(10) PRIMARY KEY,
         account_id     NUMBER(10) NOT NULL REFERENCES accounts(account_id),
         merchant_id    NUMBER(10) REFERENCES merchants(merchant_id),
         txn_ts         TIMESTAMP,
         amount_cents   NUMBER(15),
         currency       VARCHAR2(3) NOT NULL,
         channel        VARCHAR2(20) NOT NULL,
         txn_type       VARCHAR2(20) NOT NULL,
         status         VARCHAR2(20) NOT NULL,
         flag_reason    VARCHAR2(60),
         region         VARCHAR2(20) NOT NULL
       )""",
    """CREATE TABLE loans (
         loan_id        NUMBER(10) PRIMARY KEY,
         customer_id    NUMBER(10) NOT NULL REFERENCES customers(customer_id),
         branch_id      NUMBER(10) NOT NULL REFERENCES branches(branch_id),
         loan_type      VARCHAR2(20) NOT NULL,
         amount_cents   NUMBER(15),
         rate_bp        NUMBER(5),
         term_months    NUMBER(4),
         status         VARCHAR2(20) NOT NULL
       )""",
    """CREATE TABLE sar_reports (
         sar_id         NUMBER(10) PRIMARY KEY,
         customer_id    NUMBER(10) NOT NULL REFERENCES customers(customer_id),
         filed_ts       TIMESTAMP,
         reason_code    VARCHAR2(30) NOT NULL,
         narrative      VARCHAR2(1000),
         status         VARCHAR2(20) NOT NULL
       )""",
    "COMMENT ON COLUMN transactions.amount_cents IS 'Transaction amount in USD CENTS, never dollars; divide by 100 for dollars.'",
    "COMMENT ON COLUMN transactions.region IS 'Denormalized home-branch region of the transacting account; drives the Part 8 DDS row policy.'",
    "COMMENT ON COLUMN transactions.flag_reason IS 'Reason the AML rules flagged or blocked this transaction (STRUCTURING, GEO_VELOCITY, HIGH_RISK_COUNTRY, RAPID_CASH_OUT, LARGE_CASH_DEPOSIT).'",
    "COMMENT ON COLUMN accounts.balance_cents IS 'Current balance in USD CENTS, never dollars; divide by 100 for dollars.'",
    "COMMENT ON COLUMN customers.risk_rating IS '1-100 customer risk score; higher means riskier.'",
    "COMMENT ON TABLE transactions IS 'Card/account transactions; status FLAGGED or BLOCKED indicates an AML rule hit with flag_reason set.'",
    "COMMENT ON TABLE sar_reports IS 'Suspicious Activity Reports; compliance-only, restricted by the Part 8 DDS policies.'",
    "COMMENT ON TABLE branches IS 'Bank branches worldwide; location is SDO_GEOMETRY (WGS84, SRID 8307).'",
    "COMMENT ON TABLE merchants IS 'Merchants where card transactions occur; location is SDO_GEOMETRY (WGS84, SRID 8307).'",
]

SPATIAL = [
    "DELETE FROM USER_SDO_GEOM_METADATA WHERE table_name IN ('BRANCHES', 'MERCHANTS')",
    """INSERT INTO USER_SDO_GEOM_METADATA (table_name, column_name, diminfo, srid)
       VALUES ('BRANCHES', 'LOCATION',
               SDO_DIM_ARRAY(
                 SDO_DIM_ELEMENT('LON', -180, 180, 0.005),
                 SDO_DIM_ELEMENT('LAT',  -90,  90, 0.005)
               ), 8307)""",
    """INSERT INTO USER_SDO_GEOM_METADATA (table_name, column_name, diminfo, srid)
       VALUES ('MERCHANTS', 'LOCATION',
               SDO_DIM_ARRAY(
                 SDO_DIM_ELEMENT('LON', -180, 180, 0.005),
                 SDO_DIM_ELEMENT('LAT',  -90,  90, 0.005)
               ), 8307)""",
    "CREATE INDEX branches_loc_sx  ON branches(location) INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2",
    "CREATE INDEX merchants_loc_sx ON merchants(location) INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2",
]

# ---------- Reference data ---------------------------------------------------
# (branch_id, branch_code, name, city, country, region, latitude, longitude, opened_year)
BRANCHES = [
    # AMERICAS
    (1,  "NYC", "Wall Street",          "New York",     "USA",          "AMERICAS",     40.706100,  -74.008900, 1998),
    (2,  "MIA", "Brickell Avenue",       "Miami",        "USA",          "AMERICAS",     25.761700,  -80.191800, 2003),
    (3,  "CHI", "LaSalle Street",        "Chicago",      "USA",          "AMERICAS",     41.878100,  -87.629800, 1995),
    (4,  "DAL", "Main Street",           "Dallas",       "USA",          "AMERICAS",     32.776700,  -96.797000, 2008),
    (5,  "LAX", "Wilshire Boulevard",    "Los Angeles",  "USA",          "AMERICAS",     34.052200, -118.243700, 1991),
    (6,  "SEA", "Pike Street",           "Seattle",      "USA",          "AMERICAS",     47.606200, -122.332100, 2011),
    (7,  "TOR", "Bay Street",            "Toronto",      "Canada",       "AMERICAS",     43.653200,  -79.383200, 1999),
    (8,  "MEX", "Paseo de la Reforma",   "Mexico City",  "Mexico",       "AMERICAS",     19.432600,  -99.133200, 2005),
    (9,  "SAO", "Avenida Paulista",      "Sao Paulo",    "Brazil",       "AMERICAS",    -23.561400,  -46.655900, 2010),
    # EUROPE
    (10, "LON", "Canary Wharf",          "London",       "UK",           "EUROPE",       51.504800,   -0.023500, 1997),
    (11, "PAR", "Opera",                 "Paris",        "France",       "EUROPE",       48.870600,    2.335300, 2001),
    (12, "BER", "Kurfurstendamm",        "Berlin",       "Germany",      "EUROPE",       52.520000,   13.405000, 2006),
    (13, "AMS", "Herengracht",           "Amsterdam",    "Netherlands",  "EUROPE",       52.367600,    4.904100, 1994),
    (14, "ZRH", "Bahnhofstrasse",        "Zurich",       "Switzerland",  "EUROPE",       47.376900,    8.541700, 1993),
    (15, "MAD", "Gran Via",              "Madrid",       "Spain",        "EUROPE",       40.416800,   -3.703800, 2002),
    (16, "MIL", "Via Monte Napoleone",   "Milan",        "Italy",        "EUROPE",       45.464200,    9.190000, 2004),
    (17, "DUB", "IFSC",                  "Dublin",       "Ireland",      "EUROPE",       53.349800,   -6.260300, 2012),
    # MIDDLE_EAST
    (18, "DXB", "DIFC",                  "Dubai",        "UAE",          "MIDDLE_EAST",  25.204800,   55.270800, 2007),
    (19, "TLV", "Rothschild Boulevard",  "Tel Aviv",     "Israel",       "MIDDLE_EAST",  32.085300,   34.781800, 2013),
    (20, "RUH", "King Fahd Road",        "Riyadh",       "Saudi Arabia", "MIDDLE_EAST",  24.713600,   46.675300, 2015),
    # ASIA_PACIFIC
    (21, "SIN", "Raffles Place",         "Singapore",    "Singapore",    "ASIA_PACIFIC",  1.283700,  103.851500, 1996),
    (22, "HKG", "Central District",      "Hong Kong",    "Hong Kong",    "ASIA_PACIFIC", 22.279300,  114.162800, 1999),
    (23, "TYO", "Marunouchi",            "Tokyo",        "Japan",        "ASIA_PACIFIC", 35.681200,  139.767100, 1998),
    (24, "SYD", "Martin Place",          "Sydney",       "Australia",    "ASIA_PACIFIC",-33.868800,  151.209300, 2003),
    (25, "MUM", "Bandra Kurla",          "Mumbai",       "India",        "ASIA_PACIFIC", 19.076000,   72.877700, 2008),
]

BRANCHES_BY_ID = {b[0]: b for b in BRANCHES}


# (merchant_id, name, mcc_code, category, country, region, latitude, longitude)
MERCHANTS = [
    # AMERICAS
    (1,   "Whole Harvest Market",      "5411", "Groceries",        "USA",    "AMERICAS",     40.758000,  -73.985500),
    (2,   "Metro Rail Coffee",         "5812", "Cafes",            "USA",    "AMERICAS",     40.712800,  -74.006000),
    (3,   "Grand Plaza Hotel",         "7011", "Lodging",          "USA",    "AMERICAS",     40.759000,  -73.984500),
    (4,   "Delta Skies Airlines",      "4511", "Airlines",         "USA",    "AMERICAS",     33.941600,  -118.408500),
    (5,   "Beacon Electronics",        "5732", "Electronics",      "USA",    "AMERICAS",     34.052200,  -118.243700),
    (6,   "Shellstar Fuels",           "5541", "Fuel",             "USA",    "AMERICAS",     33.942500,  -118.255000),
    (7,   "Blue Orchid Dining",        "5812", "Restaurants",      "USA",    "AMERICAS",     25.761700,  -80.191800),
    (8,   "Summit View Casino",        "7995", "Casino",           "USA",    "AMERICAS",     36.114700,  -115.172800),
    (9,   "BitVault Exchange",         "6051", "Crypto exchange",  "USA",    "AMERICAS",     37.774900,  -122.419400),
    (10,  "Global Remit Now",          "4829", "Wire transfer",    "USA",    "AMERICAS",     40.712800,  -74.006000),
    (11,  "Amazonica Retail",          "5999", "General retail",   "USA",    "AMERICAS",     47.606200,  -122.332100),
    (12,  "Luxe Watches NY",           "5094", "Jewelry",          "USA",    "AMERICAS",     40.758000,  -73.985500),
    (13,  "Banco Sol ATM Network",     "6011", "ATM",              "Mexico", "AMERICAS",     19.432600,  -99.133200),
    (14,  "Fiesta Foods",              "5411", "Groceries",        "Brazil", "AMERICAS",    -23.561400,  -46.655900),
    # EUROPE
    (15,  "Harrods Knightsbridge",     "5311", "Department store", "UK",     "EUROPE",       51.499400,   -0.163700),
    (16,  "Monoprix Paris",            "5411", "Groceries",        "France", "EUROPE",       48.870600,    2.335300),
    (17,  "SkyJet Europe",             "4511", "Airlines",         "UK",     "EUROPE",       51.470000,   -0.454300),
    (18,  "Swiss Rail SBB",            "4111", "Transit",          "Switzerland", "EUROPE",  47.376900,    8.541700),
    (19,  "Lombard Street Wine",       "5921", "Liquor",           "UK",     "EUROPE",       51.513300,   -0.088600),
    (20,  "El Corte Ingles Madrid",    "5311", "Department store", "Spain",  "EUROPE",       40.416800,   -3.703800),
    (21,  "Aurum Milano",              "5094", "Jewelry",          "Italy",  "EUROPE",       45.464200,    9.190000),
    (22,  "Berlin Book Nook",          "5942", "Books",            "Germany","EUROPE",       52.520000,   13.405000),
    (23,  "Emerald Isle Golf Club",    "7997", "Recreation",       "Ireland","EUROPE",       53.349800,   -6.260300),
    (24,  "Paris Crypto Desk",         "6051", "Crypto exchange",  "France", "EUROPE",       48.856600,    2.352200),
    # MIDDLE_EAST
    (25,  "Gold Souk Exchange",        "6051", "Gold & forex",     "UAE",    "MIDDLE_EAST",  25.264400,   55.297100),
    (26,  "Desert Pearl Hotel",        "7011", "Lodging",          "UAE",    "MIDDLE_EAST",  25.204800,   55.270800),
    (27,  "CryptoDesk MENA",           "6051", "Crypto exchange",  "UAE",    "MIDDLE_EAST",  25.204800,   55.270800),
    (28,  "Tel Aviv Bistro",           "5812", "Restaurants",      "Israel", "MIDDLE_EAST",  32.085300,   34.781800),
    (29,  "Riyadh Oasis Mall",         "5311", "Department store", "Saudi Arabia", "MIDDLE_EAST", 24.713600, 46.675300),
    (30,  "Sahara Remit House",        "4829", "Wire transfer",    "UAE",    "MIDDLE_EAST",  25.264400,   55.297100),
    # ASIA_PACIFIC
    (31,  "Marina Bay Sands",          "7995", "Casino",           "Singapore", "ASIA_PACIFIC", 1.283700, 103.851500),
    (32,  "Raffles Books",             "5942", "Books",            "Singapore", "ASIA_PACIFIC", 1.290270, 103.851959),
    (33,  "Shinjuku Ginza Dept",       "5311", "Department store", "Japan",  "ASIA_PACIFIC", 35.681200,  139.767100),
    (34,  "Harbour City Mall",         "5311", "Department store", "Hong Kong", "ASIA_PACIFIC", 22.295000, 114.168000),
    (35,  "Sydney Opera Gift",         "5947", "Gifts",            "Australia", "ASIA_PACIFIC", -33.856800, 151.215300),
    (36,  "Lucky Dragon Casino",       "7995", "Casino",           "Macau", "ASIA_PACIFIC", 22.198700,  113.543900),
    (37,  "CryptoMoon Exchange",       "6051", "Crypto exchange",  "Singapore", "ASIA_PACIFIC", 1.352100, 103.819800),
    (38,  "Mumbai Spice Bazaar",       "5812", "Restaurants",      "India",  "ASIA_PACIFIC", 19.076000,   72.877700),
    (39,  "Bondi Surf Shop",           "5651", "Apparel",          "Australia", "ASIA_PACIFIC", -33.890800, 151.274300),
    (40,  "Silk Road Traders HK",      "6051", "Gold & forex",     "Hong Kong", "ASIA_PACIFIC", 22.319300, 114.169400),
]

MERCHANTS_BY_ID = {m[0]: m for m in MERCHANTS}

# High-risk corridors used by the AML patterns (merchant ids whose region /
# category the rules treat as elevated risk).
HIGH_RISK_MERCHANT_IDS = [8, 9, 10, 25, 27, 30, 31, 36, 37, 40]

FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason",
    "Isabella", "Lucas", "Mia", "James", "Amelia", "Benjamin", "Harper",
    "Elena", "Mateo", "Sofia", "Yusuf", "Fatima", "Chen", "Mei", "Ravi",
    "Ananya", "Diego", "Camila", "Hannah", "Jacob", "Priya", "Arjun",
    "Naomi", "Ezra", "Layla", "Omar", "Zainab", "Kenji", "Yuki", "Wei",
    "Chloe", "Daniel", "Grace", "Samuel", "Nora", "Leo", "Aria", "Hugo",
    "Ingrid", "Lars", "Marta", "Piotr",
]
LAST_NAMES = [
    "Johnson", "Smith", "Garcia", "Brown", "Williams", "Jones", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Reyes", "Khan", "Al-Farsi", "Tanaka", "Sato", "Sharma",
    "Patel", "Costa", "Silva", "Novak", "Kowalski", "Mueller",
]

SEGMENTS = ["RETAIL"] * 55 + ["PREMIUM"] * 20 + ["SME"] * 15 + ["CORP"] * 10

CUSTOMER_COUNTRIES = [
    "USA", "Canada", "Mexico", "Brazil", "UK", "France", "Germany", "Spain",
    "Italy", "Ireland", "Switzerland", "Netherlands", "UAE", "Israel",
    "Saudi Arabia", "Singapore", "Hong Kong", "Japan", "Australia", "India",
]

ACCOUNT_TYPES = ["CHECKING"] * 50 + ["SAVINGS"] * 30 + ["MONEY_MARKET"] * 10 + ["CREDIT_LINE"] * 10
CURRENCIES = ["USD"] * 70 + ["EUR"] * 12 + ["GBP"] * 8 + ["SGD"] * 5 + ["JPY"] * 5
CARD_TYPES = ["DEBIT"] * 60 + ["CREDIT"] * 35 + ["PREPAID"] * 5

CHANNEL_MIX = ["POS"] * 45 + ["ONLINE"] * 25 + ["ATM"] * 10 + ["WIRE"] * 5 + ["MOBILE"] * 10 + ["BRANCH"] * 5
LOAN_TYPES = ["MORTGAGE", "AUTO", "PERSONAL", "BUSINESS"]


def _drop_existing(conn):
    for v in ["account_dv", "customer_dv"]:
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP VIEW {v}")
        except oracledb.DatabaseError:
            pass
    for t in ["sar_reports", "loans", "transactions", "cards", "merchants",
              "accounts", "customers", "branches"]:
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE {t} CASCADE CONSTRAINTS PURGE")
        except oracledb.DatabaseError:
            pass


def _create_schema(conn):
    with conn.cursor() as cur:
        for stmt in DDL:
            cur.execute(stmt)
    conn.commit()


def _create_spatial(conn):
    with conn.cursor() as cur:
        for stmt in SPATIAL:
            try:
                cur.execute(stmt)
            except oracledb.DatabaseError as e:
                if e.args[0].code in (955, 1408, 13223, 13226, 29855):
                    continue
                raise
    conn.commit()


def _build_seed():
    """Generate deterministic seed data (random.seed(42)).

    Returns a dict of row lists; customers are also returned as a list of
    (customer_id, name) so the SARs and fraud patterns can reference them.
    """
    random.seed(42)
    now = _dt.datetime.utcnow()

    # ---------- customers ----------
    customers = []
    used_ssn = set()
    for cid in range(1, 201):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        while True:
            ssn = f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"
            if ssn not in used_ssn:
                used_ssn.add(ssn)
                break
        # Deliberately hotter risk ratings on a few customers get injected by
        # the fraud patterns below; the base draw keeps most customers cool.
        rr = random.randint(5, 40)
        if cid % 17 == 0:
            rr = random.randint(55, 75)
        customers.append((cid, f"{first} {last}", ssn,
                          random.choice(CUSTOMER_COUNTRIES),
                          random.choice(SEGMENTS), rr))

    # ---------- accounts (one per customer, spread across branches) ----------
    accounts = []
    opened_dates = []
    for cid in range(1, 201):
        branch = random.choice(BRANCHES)
        acc_type = random.choice(ACCOUNT_TYPES)
        opened = now - _dt.timedelta(days=random.randint(60, 3650))
        base_bal = random.randint(15_000, 900_000)
        if random.random() < 0.12:
            base_bal = random.randint(2_000_000, 25_000_000)
        accounts.append((cid, cid, branch[0], acc_type, random.choice(CURRENCIES),
                         base_bal * 100, opened, "ACTIVE"))
        opened_dates.append((cid, opened))
    # A handful of extra accounts for SME/CORP customers (multiple accounts).
    for extra in range(50):
        cid = random.randint(1, 200)
        branch = random.choice(BRANCHES)
        acc_type = random.choice(ACCOUNT_TYPES)
        opened = now - _dt.timedelta(days=random.randint(60, 3650))
        accounts.append((200 + extra, cid, branch[0], acc_type,
                         random.choice(CURRENCIES),
                         random.randint(15_000, 900_000) * 100, opened, "ACTIVE"))
    account_branch = {a[0]: a[2] for a in accounts}       # account_id -> branch_id
    account_customer = {a[0]: a[1] for a in accounts}      # account_id -> customer_id

    # ---------- cards ----------
    cards = []
    card_id = 1
    for acc_id, _, _ in [(a[0], a[1], a[2]) for a in accounts]:
        n_cards = random.choices([0, 1, 2, 3], weights=[15, 60, 20, 5])[0]
        for _ in range(n_cards):
            ctype = random.choice(CARD_TYPES)
            digits = "".join(str(random.randint(0, 9)) for _ in range(12))
            pan = ("4532" if ctype == "DEBIT" else "5412" if ctype == "CREDIT" else "6011") + digits
            cards.append((card_id, acc_id, ctype, pan,
                          now - _dt.timedelta(days=random.randint(30, 900)),
                          "ACTIVE", random.randint(500, 5000) * 100))
            card_id += 1
    card_account = {c[0]: c[1] for c in cards}

    # ---------- transactions ----------
    transactions = []
    txn_id = 1

    def add_txn(account_id, merchant_id, when, amount_cents, channel, txn_type,
                status="COMPLETED", flag_reason=None):
        nonlocal txn_id
        region = BRANCHES_BY_ID[account_branch[account_id]][5]
        transactions.append((txn_id, account_id, merchant_id, when, amount_cents,
                             "USD", channel, txn_type, status, flag_reason, region))
        txn_id += 1

    # Base activity: 2-7 ordinary transactions per account over the last 90 days.
    for acc_id, cust_id, _ in [(a[0], a[1], a[2]) for a in accounts]:
        for _ in range(random.randint(2, 7)):
            channel = random.choice(CHANNEL_MIX)
            when = now - _dt.timedelta(days=random.uniform(0, 90), hours=random.uniform(0, 24))
            if channel in ("POS", "ONLINE"):
                m = random.choice(MERCHANTS)
                amount = random.randint(500, 200_000)
                ttype = "PURCHASE" if random.random() < 0.8 else "CARD_PAYMENT"
            elif channel == "ATM":
                m = None
                amount = random.randint(2_000, 100_000)
                ttype = "WITHDRAWAL" if random.random() < 0.8 else "DEPOSIT"
            elif channel == "WIRE":
                m = None
                amount = random.randint(100_000, 10_000_000)
                ttype = "WIRE_IN" if random.random() < 0.5 else "WIRE_OUT"
            elif channel == "MOBILE":
                m = None
                amount = random.randint(500, 50_000)
                ttype = "TRANSFER"
            else:  # BRANCH
                m = None
                amount = random.randint(10_000, 5_000_000)
                ttype = "DEPOSIT" if random.random() < 0.5 else "WITHDRAWAL"
            add_txn(acc_id, m if m else None, when, amount, channel, ttype)

    # ---------- Fraud patterns (deliberately seeded AML signals) ------------
    # 1. STRUCTURING — several cash deposits just under the $10k CTR threshold
    #    within a short window.
    for cust_seed in [7, 42, 88, 133]:
        cust_id = cust_seed
        acc = next(a for a in accounts if a[1] == cust_id)
        start = now - _dt.timedelta(days=random.randint(12, 20))
        for i in range(random.randint(8, 12)):
            when = start + _dt.timedelta(hours=i * random.randint(9, 26))
            add_txn(acc[0], None, when, random.randint(800_000, 999_900),
                    "BRANCH" if i % 2 == 0 else "ATM", "DEPOSIT",
                    status="FLAGGED", flag_reason="STRUCTURING")

    # 2. GEO_VELOCITY — a home-region card purchase, then a purchase in a far
    #    region within hours (impossible geography), one blocked attempt.
    for cust_seed in [19, 55, 91]:
        cust_id = cust_seed
        acc = next(a for a in accounts if a[1] == cust_id)
        home_region = BRANCHES_BY_ID[acc[2]][5]
        far_merchants = [m for m in MERCHANTS if m[5] != home_region]
        when0 = now - _dt.timedelta(days=random.randint(3, 10))
        add_txn(acc[0], next(m for m in MERCHANTS if m[5] == home_region)[0],
                when0, random.randint(2_000, 20_000), "POS", "PURCHASE")
        add_txn(acc[0], random.choice(far_merchants)[0],
                when0 + _dt.timedelta(hours=random.randint(1, 4)),
                random.randint(5_000, 80_000), "POS", "PURCHASE",
                status="FLAGGED", flag_reason="GEO_VELOCITY")
        add_txn(acc[0], random.choice(far_merchants)[0],
                when0 + _dt.timedelta(hours=random.randint(2, 3)),
                random.randint(5_000, 80_000), "POS", "PURCHASE",
                status="BLOCKED", flag_reason="GEO_VELOCITY")

    # 3. HIGH_RISK_COUNTRY — wire-outs to merchants in elevated-risk corridors
    #    shortly after an inbound credit.
    for cust_seed in [23, 71, 140, 162]:
        cust_id = cust_seed
        acc = next(a for a in accounts if a[1] == cust_id)
        when = now - _dt.timedelta(days=random.randint(2, 12))
        add_txn(acc[0], None, when, random.randint(500_000, 5_000_000),
                "WIRE", "WIRE_IN")
        for _ in range(random.randint(2, 4)):
            m = MERCHANTS_BY_ID[random.choice(HIGH_RISK_MERCHANT_IDS)]
            add_txn(acc[0], m[0], when + _dt.timedelta(hours=random.randint(1, 40)),
                    random.randint(100_000, 2_000_000), "WIRE", "WIRE_OUT",
                    status="FLAGGED", flag_reason="HIGH_RISK_COUNTRY")

    # 4. RAPID_CASH_OUT — large inbound wire, then ATM withdrawals draining it.
    for cust_seed in [30, 117]:
        cust_id = cust_seed
        acc = next(a for a in accounts if a[1] == cust_id)
        when = now - _dt.timedelta(days=random.randint(1, 6))
        add_txn(acc[0], None, when, random.randint(10_000_000, 40_000_000),
                "WIRE", "WIRE_IN")
        for i in range(random.randint(5, 7)):
            add_txn(acc[0], None, when + _dt.timedelta(hours=i * random.randint(3, 8)),
                    random.randint(50_000, 100_000), "ATM", "WITHDRAWAL",
                    status="FLAGGED", flag_reason="RAPID_CASH_OUT")

    # 5. LARGE_CASH_DEPOSIT — single > $50k cash deposit.
    for cust_seed in [44, 158]:
        cust_id = cust_seed
        acc = next(a for a in accounts if a[1] == cust_id)
        add_txn(acc[0], None, now - _dt.timedelta(days=random.randint(1, 9)),
                random.randint(5_500_000, 12_000_000), "BRANCH", "DEPOSIT",
                status="FLAGGED", flag_reason="LARGE_CASH_DEPOSIT")

    # ---------- loans ----------
    loans = []
    for loan_id in range(1, 61):
        cust_id = random.randint(1, 200)
        branch = random.choice(BRANCHES)
        ltype = random.choice(LOAN_TYPES)
        if ltype == "MORTGAGE":
            amt, term = random.randint(20_000_000, 150_000_000), random.choice([180, 240, 360])
        elif ltype == "AUTO":
            amt, term = random.randint(1_500_000, 6_000_000), random.choice([36, 48, 60])
        elif ltype == "PERSONAL":
            amt, term = random.randint(500_000, 5_000_000), random.choice([12, 24, 36])
        else:
            amt, term = random.randint(5_000_000, 50_000_000), random.choice([24, 36, 60])
        loans.append((loan_id, cust_id, branch[0], ltype, amt,
                      random.randint(350, 850), term,
                      random.choice(["ACTIVE", "ACTIVE", "ACTIVE", "PAID_OFF", "DEFAULTED"])))

    # ---------- SAR reports ----------
    sar_customers = [7, 19, 23, 30, 42, 44, 55, 71, 88, 91, 117, 133, 140, 158, 162]
    sar_narratives = {
        "STRUCTURING": ("Multiple cash deposits between $8,000 and $9,999 within a "
                        "short window, consistent with structuring to avoid the "
                        "$10,000 CTR threshold."),
        "GEO_VELOCITY": ("Card purchases in geographically distant regions within "
                         "hours of each other, inconsistent with travel patterns."),
        "HIGH_RISK_COUNTRY": ("Wire transfers to merchants in elevated-risk "
                              "corridors shortly after inbound credits."),
        "RAPID_CASH_OUT": ("Large inbound wire followed by rapid ATM withdrawals "
                           "draining the account within 48 hours."),
        "LARGE_CASH_DEPOSIT": ("Single cash deposit exceeding $50,000 without a "
                               "plausible source of funds."),
    }
    sar_reports = []
    for i, cust_id in enumerate(sar_customers):
        reason = random.choice(FLAG_REASONS)
        sar_reports.append((i + 1, cust_id,
                            now - _dt.timedelta(days=random.randint(1, 30)),
                            reason, sar_narratives[reason],
                            random.choice(["UNDER_REVIEW", "FILED", "OPEN"])))

    return {
        "customers": customers,
        "accounts": accounts,
        "cards": cards,
        "transactions": transactions,
        "loans": loans,
        "sar_reports": sar_reports,
    }


def _insert_data(conn, seed_data):
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO branches (branch_id, branch_code, name, city, country, region, "
            "                      latitude, longitude, location, opened_year) "
            "VALUES (:id, :code, :name, :city, :country, :region, :lat, :lon, "
            "        SDO_GEOMETRY(2001, 8307, SDO_POINT_TYPE(:lon, :lat, NULL), NULL, NULL), :year)",
            [
                {"id": b[0], "code": b[1], "name": b[2], "city": b[3],
                 "country": b[4], "region": b[5], "lat": b[6], "lon": b[7], "year": b[8]}
                for b in BRANCHES
            ],
        )
        cur.executemany(
            "INSERT INTO merchants (merchant_id, name, mcc_code, category, country, "
            "                       region, latitude, longitude, location) "
            "VALUES (:id, :name, :mcc, :cat, :country, :region, :lat, :lon, "
            "        SDO_GEOMETRY(2001, 8307, SDO_POINT_TYPE(:lon, :lat, NULL), NULL, NULL))",
            [
                {"id": m[0], "name": m[1], "mcc": m[2], "cat": m[3],
                 "country": m[4], "region": m[5], "lat": m[6], "lon": m[7]}
                for m in MERCHANTS
            ],
        )
        cur.executemany(
            "INSERT INTO customers VALUES (:1, :2, :3, :4, :5, :6)",
            seed_data["customers"],
        )
        cur.executemany(
            "INSERT INTO accounts VALUES (:1, :2, :3, :4, :5, :6, :7, :8)",
            seed_data["accounts"],
        )
        cur.executemany(
            "INSERT INTO cards VALUES (:1, :2, :3, :4, :5, :6, :7)",
            seed_data["cards"],
        )
        cur.executemany(
            "INSERT INTO transactions VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11)",
            seed_data["transactions"],
        )
        cur.executemany(
            "INSERT INTO loans VALUES (:1, :2, :3, :4, :5, :6, :7, :8)",
            seed_data["loans"],
        )
        cur.executemany(
            "INSERT INTO sar_reports VALUES (:1, :2, :3, :4, :5, :6)",
            seed_data["sar_reports"],
        )
    conn.commit()


# ---------- Duality views ----------------------------------------------------
DV_DDL = [
    """CREATE OR REPLACE JSON RELATIONAL DUALITY VIEW account_dv AS
       SELECT JSON {
         '_id'          : a.account_id,
         'accountType'  : a.account_type,
         'currency'     : a.currency,
         'balanceCents' : a.balance_cents,
         'status'       : a.status,
         'openedTs'     : a.opened_ts,
         'region'       : (SELECT JSON {
                              'branchCode' : b.branch_code, 'name' : b.name,
                              'city' : b.city, 'country' : b.country,
                              'region' : b.region
                            } FROM branches b WHERE b.branch_id = a.branch_id),
         'customer'     : (SELECT JSON {
                              'customerId' : cu.customer_id, 'fullName' : cu.full_name,
                              'ssn' : cu.ssn, 'segment' : cu.segment,
                              'riskRating' : cu.risk_rating
                            } FROM customers cu WHERE cu.customer_id = a.customer_id),
         'cards'        : [SELECT JSON {
                              'cardId' : ca.card_id, 'cardType' : ca.card_type,
                              'cardNumber' : ca.card_number, 'status' : ca.status,
                              'dailyLimitCents' : ca.daily_limit_cents
                            } FROM cards ca WHERE ca.account_id = a.account_id],
         'transactions' : [SELECT JSON {
                              'txnId' : t.txn_id, 'txnTs' : t.txn_ts,
                              'amountCents' : t.amount_cents, 'currency' : t.currency,
                              'channel' : t.channel, 'txnType' : t.txn_type,
                              'status' : t.status, 'flagReason' : t.flag_reason,
                              'region' : t.region,
                              'merchant' : (SELECT JSON {
                                              'merchantId' : m.merchant_id,
                                              'name' : m.name, 'mccCode' : m.mcc_code,
                                              'category' : m.category,
                                              'country' : m.country
                                            } FROM merchants m WHERE m.merchant_id = t.merchant_id)
                            } FROM transactions t WHERE t.account_id = a.account_id]
       } FROM accounts a""",

    """CREATE OR REPLACE JSON RELATIONAL DUALITY VIEW customer_dv AS
       SELECT JSON {
         '_id'         : cu.customer_id,
         'fullName'    : cu.full_name,
         'ssn'         : cu.ssn,
         'segment'     : cu.segment,
         'riskRating'  : cu.risk_rating,
         'country'     : cu.country,
         'accounts'    : [SELECT JSON {
                            'accountId' : a.account_id, 'accountType' : a.account_type,
                            'currency' : a.currency, 'balanceCents' : a.balance_cents,
                            'status' : a.status,
                            'branch' : (SELECT JSON {
                                          'branchCode' : b.branch_code, 'name' : b.name,
                                          'city' : b.city, 'region' : b.region
                                        } FROM branches b WHERE b.branch_id = a.branch_id)
                          } FROM accounts a WHERE a.customer_id = cu.customer_id],
         'loans'       : [SELECT JSON {
                            'loanId' : l.loan_id, 'loanType' : l.loan_type,
                            'amountCents' : l.amount_cents, 'rateBp' : l.rate_bp,
                            'termMonths' : l.term_months, 'status' : l.status
                          } FROM loans l WHERE l.customer_id = cu.customer_id]
       } FROM customers cu""",
]


def _create_duality_views(conn):
    for stmt in DV_DDL:
        try:
            with conn.cursor() as cur:
                cur.execute(stmt)
            head = stmt.strip().split("\n", 1)[0]
            print(f"  OK: {head[:80]}")
        except oracledb.DatabaseError as e:
            code_ = e.args[0].code
            if code_ in (900, 901, 922, 2000):
                print(f"  !! duality view DDL not supported on this image (ORA-{code_:05d}); skipping")
                return
            raise
    conn.commit()


def seed(conn):
    """Run the full pipeline: drop → create → spatial → seed → duality views."""
    print("Dropping existing bank objects...")
    _drop_existing(conn)

    print("Creating tables...")
    _create_schema(conn)

    print("Wiring spatial metadata + indexes...")
    _create_spatial(conn)

    print("Generating deterministic seed data...")
    data = _build_seed()

    print(f"Inserting: {len(BRANCHES)} branches, {len(MERCHANTS)} merchants, "
          f"{len(data['customers'])} customers, {len(data['accounts'])} accounts, "
          f"{len(data['cards'])} cards, {len(data['transactions'])} transactions, "
          f"{len(data['loans'])} loans, {len(data['sar_reports'])} SAR reports...")
    _insert_data(conn, data)

    print("Creating JSON Relational Duality Views (account_dv, customer_dv)...")
    _create_duality_views(conn)

    flagged = sum(1 for t in data["transactions"] if t[8] in ("FLAGGED", "BLOCKED"))
    print(f"\nFINANCE seeded. {flagged} transactions carry an AML flag/block.")
