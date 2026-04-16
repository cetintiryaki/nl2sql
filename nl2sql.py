"""
nl2sql.py - Natural language → SQL via Ollama (llama3)

Sends a structured prompt to the local Ollama instance and
extracts a clean SQL statement from the response.
"""

import re
import requests
from typing import Optional

from schema import get_schema_description

OLLAMA_URL   = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3"


SYSTEM_PROMPT = """You are a SQL expert assistant for a fintech banking application.
Your job is to convert natural language questions into safe SQLite queries.

Rules:
- Output ONLY the SQL query, nothing else
- Do NOT use DROP, DELETE, TRUNCATE, ALTER, CREATE, ATTACH, PRAGMA
- Always use proper JOINs when referencing multiple tables
- For money/balance columns use proper rounding: ROUND(balance, 2)
- Do NOT add markdown formatting, no ```sql blocks, just raw SQL
- End the query with a semicolon

{schema}
""".strip()


class NL2SQL:
    def __init__(self, model: str = DEFAULT_MODEL, ollama_url: str = OLLAMA_URL):
        self.model      = model
        self.ollama_url = ollama_url
        self._schema    = get_schema_description()

    def translate(self, user_input: str) -> Optional[str]:
        """
        Convert a natural language query to SQL.
        Returns the SQL string, or None if Ollama is unreachable.
        """
        prompt = self._build_prompt(user_input)

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model"  : self.model,
                    "prompt" : prompt,
                    "stream" : False,
                    "options": {
                        "temperature": 0.1,   # low temp → deterministic SQL
                        "num_predict": 256,
                    },
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Could not connect to Ollama. Is it running?\n"
                "Start it with:  ollama serve"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama request timed out (>60s)")

        raw = resp.json().get("response", "").strip()
        return self._extract_sql(raw)

    # ── internals ─────────────────────────────────────────────────────────────

    def _build_prompt(self, user_input: str) -> str:
        system = SYSTEM_PROMPT.format(schema=self._schema)
        return (
            f"{system}\n\n"
            f"User request: {user_input}\n\n"
            f"SQL query:"
        )

    @staticmethod
    def _extract_sql(raw: str) -> Optional[str]:
        """Strip markdown fences and extra prose, return just the SQL."""
        # Remove ```sql ... ``` fences
        fenced = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if fenced:
            raw = fenced.group(1).strip()

        # Take only lines that look like SQL (start with a SQL keyword or whitespace)
        sql_keywords = r"^(SELECT|INSERT|UPDATE|WITH|EXPLAIN|\s)"
        lines = [
            line for line in raw.splitlines()
            if re.match(sql_keywords, line, re.IGNORECASE)
        ]
        sql = "\n".join(lines).strip()

        # Fallback: just use the whole response if filtering killed everything
        if not sql:
            sql = raw

        # Remove trailing semicolon (guardrails will add LIMIT before it)
        sql = sql.rstrip(";").strip()
        return sql if sql else None
