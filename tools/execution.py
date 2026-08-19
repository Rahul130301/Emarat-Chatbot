import re
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import run_with_connection

# Fast mode has no validate_sql step, so run_sql enforces the same read-only
# guarantee itself rather than trusting the query it was handed.
FORBIDDEN_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create)\b", re.IGNORECASE
)

MAX_ROWS = 50

def _sanitize_query(query: str) -> str:
    q = query
    q = re.sub(r'(?i)\bfrom\s+aviation-uplifts\b', 'FROM [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bjoin\s+aviation-uplifts\b', 'JOIN [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bfrom\s+aviation_uplifts(?:_warehouse)?\b', 'FROM [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bjoin\s+aviation_uplifts(?:_warehouse)?\b', 'JOIN [dbo].[aviation-uplifts]', q)
    return q

@tool(approval_mode="never_require")
def run_sql(
    query: Annotated[str, Field(description="A read-only SELECT query to execute. Where validate_sql is available, call it first and only run a query it reported VALID.")],
) -> str:
    stripped = _sanitize_query(query).strip().rstrip(";")
    if not stripped.lower().startswith("select"):
        return "Error: only SELECT queries are allowed."
    if FORBIDDEN_PATTERN.search(stripped):
        return "Error: query contains a forbidden write/DDL keyword. Read-only queries only."

    def _run(conn):
        conn.timeout = 5  # seconds — pyodbc's equivalent of statement_timeout
        with conn.cursor() as cur:
            cur.execute(stripped)
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
        return colnames, rows

    try:
        colnames, rows = run_with_connection(_run)
    except Exception as e:
        return f"SQL error: {e}"

    shown = rows[:MAX_ROWS]
    # State the row count explicitly so the answer can quote a number it was
    # actually given, instead of inferring one from the query's TOP clause and
    # then displaying a different number of rows.
    if len(rows) > len(shown):
        header = (
            f"ROWS RETURNED: {len(shown)} (query matched {len(rows)}; truncated to "
            f"the first {MAX_ROWS}). Report this as a sample, not the full set."
        )
    else:
        header = f"ROWS RETURNED: {len(shown)}"
    body = "\n".join(str(tuple(r)) for r in shown)
    return f"{header}\n{colnames}\n{body}"