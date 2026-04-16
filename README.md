# NL2SQL — Natural Language Database Interface

Query a fintech SQLite database using plain English, powered by a local LLM (Ollama + llama3). Every query passes through a safety layer before execution.

```
  > Show me all users with a savings account balance over $5000

  Generated SQL: SELECT u.name, a.balance FROM users u
                 JOIN accounts a ON u.id = a.user_id
                 WHERE a.account_type = 'savings' AND a.balance > 5000 LIMIT 100

  name           balance
  -------------- --------
  Alice Johnson  8432.10
  Carol White    22100.50
  Eve Davis      6789.00

  3 row(s)
```

## Features

| Layer | What it does |
|---|---|
| **NL → SQL** | Ollama (llama3) translates English to SQLite |
| **Keyword blacklist** | Blocks DROP, DELETE, TRUNCATE, ALTER, CREATE, ATTACH |
| **Table whitelist** | Only `users`, `accounts`, `transactions`, `audit_log` allowed |
| **Read-only mode** | Toggle to block all INSERT/UPDATE operations |
| **Auto LIMIT** | Automatically adds `LIMIT 100` to unbounded SELECT queries |
| **Audit log** | Every query (including blocked ones) is logged to the DB |

## Architecture

```
nl2sql/
├── main.py        # Interactive CLI, result rendering
├── nl2sql.py      # Ollama API client, prompt engineering, SQL extraction
├── guardrails.py  # Safety checks (blacklist, whitelist, read-only, LIMIT)
├── schema.py      # SQLite schema creation + demo data seeding
└── README.md
```

## Requirements

- Python 3.8+
- [Ollama](https://ollama.com) running locally with llama3

```bash
# Install Ollama, then:
ollama pull llama3
ollama serve        # runs on localhost:11434
```

```bash
pip install requests
```

## Usage

```bash
# Normal mode (read + write)
python main.py

# Read-only mode (no writes allowed)
python main.py --read-only

# Use a different model
python main.py --model mistral
```

### Example Queries

```
> How many users are there?
> Show me the 5 largest transactions
> What is the total balance across all checking accounts?
> List all pending transactions from the last 30 days
> Show users who have both a checking and a savings account
> Update the balance of account 1 to 9999.99    ← blocked if read-only
> DROP TABLE users                               ← always blocked
```

### CLI Commands

| Command | Description |
|---|---|
| `/schema` | Show database schema |
| `/history [N]` | Show last N audit log entries |
| `/readonly on\|off` | Toggle read-only mode |
| `/help` | Show all commands |
| `/quit` | Exit |

## Security Design

```
User Input (English)
       │
       ▼
  ┌─────────────┐
  │  Ollama LLM │  ← generates SQL
  └──────┬──────┘
         │
         ▼
  ┌──────────────────────────────────┐
  │         SQLGuard                 │
  │  1. Blocked keyword check        │
  │  2. Table whitelist check        │
  │  3. Read-only mode check         │
  │  4. Auto LIMIT injection         │
  │  5. Audit log write              │
  └──────┬───────────────────────────┘
         │ allowed?
    Yes  │              No
         ▼               ▼
   Execute SQL      Show error + log
         │
         ▼
    Return results
```
