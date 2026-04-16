"""
schema.py - Demo fintech SQLite database setup

Tables:
  users        — bank customers
  accounts     — bank accounts (checking, savings)
  transactions — financial transactions
  audit_log    — all NL2SQL queries and their outcomes
"""

import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "fintech.db"


def create_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    _seed_data(conn)
    return conn


def get_schema_description(path: str = DB_PATH) -> str:
    """Return a human-readable schema string for the LLM prompt."""
    return """
Database: fintech.db (SQLite)

Tables:

users(id INTEGER PK, name TEXT, email TEXT, created_at TEXT)

accounts(id INTEGER PK, user_id INTEGER FK→users.id,
         account_type TEXT CHECK('checking','savings'),
         balance REAL, currency TEXT DEFAULT 'USD',
         is_active INTEGER DEFAULT 1, created_at TEXT)

transactions(id INTEGER PK, from_account_id INTEGER FK→accounts.id,
             to_account_id INTEGER FK→accounts.id,
             amount REAL, description TEXT,
             status TEXT CHECK('completed','pending','failed'),
             created_at TEXT)

audit_log(id INTEGER PK, user_input TEXT, generated_sql TEXT,
          was_blocked INTEGER, block_reason TEXT, executed_at TEXT)
""".strip()


# ── private ───────────────────────────────────────────────────────────────────

def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        email      TEXT    UNIQUE NOT NULL,
        created_at TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        account_type TEXT    NOT NULL CHECK(account_type IN ('checking','savings')),
        balance      REAL    NOT NULL DEFAULT 0.0,
        currency     TEXT    NOT NULL DEFAULT 'USD',
        is_active    INTEGER NOT NULL DEFAULT 1,
        created_at   TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        from_account_id INTEGER REFERENCES accounts(id),
        to_account_id   INTEGER REFERENCES accounts(id),
        amount          REAL    NOT NULL,
        description     TEXT,
        status          TEXT    NOT NULL CHECK(status IN ('completed','pending','failed')),
        created_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_input   TEXT,
        generated_sql TEXT,
        was_blocked  INTEGER DEFAULT 0,
        block_reason TEXT,
        executed_at  TEXT    DEFAULT (datetime('now'))
    );
    """)
    conn.commit()


def _seed_data(conn: sqlite3.Connection) -> None:
    # Skip if already seeded
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    users = [
        ("Alice Johnson", "alice@example.com"),
        ("Bob Smith",     "bob@example.com"),
        ("Carol White",   "carol@example.com"),
        ("David Brown",   "david@example.com"),
        ("Eve Davis",     "eve@example.com"),
    ]
    conn.executemany("INSERT INTO users(name, email) VALUES (?,?)", users)

    accounts = []
    for user_id in range(1, 6):
        accounts.append((user_id, "checking", round(random.uniform(500, 10000), 2)))
        accounts.append((user_id, "savings",  round(random.uniform(1000, 50000), 2)))
    conn.executemany(
        "INSERT INTO accounts(user_id, account_type, balance) VALUES (?,?,?)",
        accounts
    )

    now = datetime.now()
    txns = []
    for _ in range(30):
        from_id  = random.randint(1, 10)
        to_id    = random.randint(1, 10)
        if from_id == to_id:
            to_id = (to_id % 10) + 1
        amount   = round(random.uniform(10, 2000), 2)
        days_ago = random.randint(0, 90)
        ts       = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        status   = random.choice(["completed", "completed", "completed", "pending", "failed"])
        desc     = random.choice(["Payment", "Transfer", "Refund", "Purchase", "Subscription"])
        txns.append((from_id, to_id, amount, desc, status, ts))

    conn.executemany(
        "INSERT INTO transactions(from_account_id, to_account_id, amount, description, status, created_at) VALUES (?,?,?,?,?,?)",
        txns
    )
    conn.commit()
