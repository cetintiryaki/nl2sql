"""
main.py - NL2SQL CLI

An interactive terminal interface for querying a fintech SQLite database
using plain English, powered by Ollama (llama3).

Usage:
  python main.py              # interactive mode (default)
  python main.py --read-only  # block all write operations
  python main.py --model mistral

Commands inside the CLI:
  Any English sentence   → translated to SQL and executed
  /schema                → show database schema
  /history               → show recent audit log
  /readonly on|off       → toggle read-only mode
  /help                  → show commands
  /quit                  → exit
"""

import argparse
import sqlite3
import sys
import textwrap
from typing import Optional

from schema    import create_db, DB_PATH
from guardrails import SQLGuard
from nl2sql    import NL2SQL


# ── Colors (ANSI) ─────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"

def color(text: str, *codes: str) -> str:
    return "".join(codes) + text + C.RESET


# ── Result printing ───────────────────────────────────────────────────────────

def print_results(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print(color("  (no rows returned)", C.GRAY))
        return

    keys = rows[0].keys()
    col_widths = {k: max(len(k), max(len(str(r[k])) for r in rows)) for k in keys}

    header = "  " + "  ".join(k.ljust(col_widths[k]) for k in keys)
    sep    = "  " + "  ".join("-" * col_widths[k] for k in keys)

    print(color(header, C.BOLD))
    print(color(sep, C.GRAY))
    for row in rows:
        line = "  " + "  ".join(str(row[k]).ljust(col_widths[k]) for k in keys)
        print(line)

    print(color(f"\n  {len(rows)} row(s)", C.GRAY))


# ── CLI App ───────────────────────────────────────────────────────────────────

class App:
    def __init__(self, model: str, read_only: bool):
        print(color("\n  NL2SQL — Natural Language Database Interface", C.BOLD + C.CYAN))
        print(color("  Powered by Ollama + llama3  |  fintech demo DB\n", C.GRAY))

        print("  Initializing database...", end=" ", flush=True)
        self.conn  = create_db(DB_PATH)
        print(color("OK", C.GREEN))

        print(f"  Loading model '{model}'...", end=" ", flush=True)
        self.nl2sql = NL2SQL(model=model)
        print(color("OK", C.GREEN))

        self.guard     = SQLGuard(read_only=read_only)
        self.read_only = read_only

        mode_str = color("READ-ONLY", C.YELLOW) if read_only else color("READ-WRITE", C.GREEN)
        print(f"  Mode: {mode_str}")
        print(color("  Type /help for commands\n", C.GRAY))

    def run(self) -> None:
        while True:
            try:
                user_input = input(color("  > ", C.BOLD + C.CYAN)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_query(user_input)

        print(color("\n  Goodbye!\n", C.GRAY))

    # ── query flow ────────────────────────────────────────────────────────────

    def _handle_query(self, user_input: str) -> None:
        # 1. Translate
        print(color("  Thinking...", C.GRAY), end="\r", flush=True)
        try:
            sql = self.nl2sql.translate(user_input)
        except RuntimeError as e:
            print(color(f"\n  ✗ {e}", C.RED))
            return

        if not sql:
            print(color("  ✗ Could not generate SQL from that input.", C.RED))
            return

        print(f"  {color('Generated SQL:', C.GRAY)} {color(sql, C.YELLOW)}")

        # 2. Guardrails
        result = self.guard.check_and_log(sql, user_input, self.conn)

        if not result.allowed:
            print(color(f"  ✗ BLOCKED: {result.reason}", C.RED))
            return

        final_sql = result.sql
        if final_sql != sql:
            print(f"  {color('Modified SQL:', C.GRAY)}  {color(final_sql, C.YELLOW)}")

        # 3. Execute
        try:
            cursor = self.conn.execute(final_sql)
            self.conn.commit()

            rows = cursor.fetchall() if cursor.description else []
            if rows:
                print()
                print_results(rows)
            else:
                affected = cursor.rowcount
                print(color(f"  ✓ Query executed. Rows affected: {affected}", C.GREEN))
        except sqlite3.Error as e:
            print(color(f"  ✗ SQL Error: {e}", C.RED))

        print()

    # ── commands ──────────────────────────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        parts = cmd.lower().split()

        if parts[0] == "/help":
            print(textwrap.dedent(f"""
  {color('Commands:', C.BOLD)}
    /schema          Show database schema
    /history [N]     Show last N audit log entries (default 10)
    /readonly on|off Toggle read-only mode
    /help            Show this help
    /quit            Exit
            """))

        elif parts[0] == "/schema":
            from schema import get_schema_description
            print(color(get_schema_description(), C.CYAN))
            print()

        elif parts[0] == "/history":
            n = int(parts[1]) if len(parts) > 1 else 10
            rows = self.conn.execute(
                """SELECT id, substr(user_input,1,40) as input,
                          was_blocked, block_reason, executed_at
                   FROM audit_log ORDER BY id DESC LIMIT ?""",
                (n,)
            ).fetchall()
            print()
            print_results(rows)
            print()

        elif parts[0] == "/readonly":
            if len(parts) > 1 and parts[1] == "on":
                self.guard.read_only = True
                print(color("  Read-only mode: ON", C.YELLOW))
            elif len(parts) > 1 and parts[1] == "off":
                self.guard.read_only = False
                print(color("  Read-only mode: OFF", C.GREEN))
            else:
                status = "ON" if self.guard.read_only else "OFF"
                print(f"  Read-only mode: {status}")
            print()

        elif parts[0] in ("/quit", "/exit", "/q"):
            raise KeyboardInterrupt

        else:
            print(color(f"  Unknown command: {cmd}  (type /help)", C.RED))
            print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="NL2SQL — Natural Language to SQLite")
    parser.add_argument("--model",     default="llama3",  help="Ollama model name")
    parser.add_argument("--read-only", action="store_true", help="Block all writes")
    args = parser.parse_args()

    app = App(model=args.model, read_only=args.read_only)
    app.run()


if __name__ == "__main__":
    main()
