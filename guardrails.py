"""
guardrails.py - SQL safety layer

Checks every generated SQL query before execution:
  1. Keyword blacklist  — blocks destructive operations
  2. Table whitelist    — only known tables allowed
  3. Read-only mode     — optionally block all writes
  4. Row limit          — forces LIMIT on SELECT queries
  5. Audit logging      — every query (blocked or not) is logged
"""

import re
import sqlite3
from dataclasses import dataclass
from typing import Optional


# ── Config ────────────────────────────────────────────────────────────────────

ALLOWED_TABLES = {"users", "accounts", "transactions", "audit_log"}

BLOCKED_KEYWORDS = [
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bDELETE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bPRAGMA\b",
    r"\bVACUUM\b",
]

MAX_ROWS = 100     # auto-add LIMIT if missing


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GuardResult:
    allowed: bool
    sql: str                        # possibly modified (LIMIT injected)
    reason: Optional[str] = None    # set if blocked


# ── Main guard ────────────────────────────────────────────────────────────────

class SQLGuard:
    def __init__(self, read_only: bool = False):
        self.read_only = read_only

    def check(self, sql: str) -> GuardResult:
        sql = sql.strip().rstrip(";")
        upper = sql.upper()

        # 1. Blocked keywords
        for pattern in BLOCKED_KEYWORDS:
            if re.search(pattern, upper):
                keyword = pattern.replace(r"\b", "").strip()
                return GuardResult(
                    allowed=False,
                    sql=sql,
                    reason=f"Blocked keyword detected: {keyword}"
                )

        # 2. Table whitelist — extract table names and check
        referenced = _extract_tables(sql)
        unknown    = referenced - ALLOWED_TABLES
        if unknown:
            return GuardResult(
                allowed=False,
                sql=sql,
                reason=f"Unknown table(s): {', '.join(unknown)}"
            )

        # 3. Read-only mode
        write_ops = re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE|UPSERT)\b", upper)
        if self.read_only and write_ops:
            return GuardResult(
                allowed=False,
                sql=sql,
                reason="Write operation blocked: read-only mode is ON"
            )

        # 4. Inject LIMIT on SELECT if missing
        if upper.lstrip().startswith("SELECT") and "LIMIT" not in upper:
            sql = f"{sql} LIMIT {MAX_ROWS}"

        return GuardResult(allowed=True, sql=sql)

    def check_and_log(
        self,
        sql: str,
        user_input: str,
        conn: sqlite3.Connection,
    ) -> GuardResult:
        result = self.check(sql)
        conn.execute(
            """INSERT INTO audit_log(user_input, generated_sql, was_blocked, block_reason)
               VALUES (?, ?, ?, ?)""",
            (
                user_input,
                sql,
                0 if result.allowed else 1,
                result.reason,
            ),
        )
        conn.commit()
        return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_tables(sql: str) -> set[str]:
    """
    Naively extract table names after FROM, JOIN, INTO, UPDATE.
    Good enough for simple single-statement queries.
    """
    pattern = r"(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([`\"\[]?[\w]+[`\"\]]?)"
    matches = re.findall(pattern, sql, re.IGNORECASE)
    return {m.strip('`"[]').lower() for m in matches}
