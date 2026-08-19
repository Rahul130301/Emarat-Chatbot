# tools/validation.py
import re
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import run_with_connection

FORBIDDEN_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create)\b", re.IGNORECASE
)

def _sanitize_query(query: str) -> str:
    q = query
    q = re.sub(r'(?i)\bfrom\s+aviation-uplifts\b', 'FROM [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bjoin\s+aviation-uplifts\b', 'JOIN [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bfrom\s+aviation_uplifts(?:_warehouse)?\b', 'FROM [dbo].[aviation-uplifts]', q)
    q = re.sub(r'(?i)\bjoin\s+aviation_uplifts(?:_warehouse)?\b', 'JOIN [dbo].[aviation-uplifts]', q)
    return q

def _order_by_needs_offset(query: str) -> bool:
    """SQL Server forbids a bare ORDER BY inside a derived table/subquery
    unless TOP or OFFSET is also present. We wrap every query in one below to
    validate it without fetching rows, so a plain 'GROUP BY x ORDER BY y DESC'
    query (a completely normal, valid query on its own) would otherwise always
    fail validation. Detect that case so we can neutralize it before wrapping."""
    if not re.search(r"(?i)\border\s+by\b", query):
        return False
    return not re.search(r"(?i)\b(top\s*\(|top\s+\d|offset\s+\d)", query)


@tool(approval_mode="never_require")
def validate_sql(
    query: Annotated[str, Field(description="The SQL SELECT query to validate before executing it.")],
) -> str:
    sanitized = _sanitize_query(query)
    stripped = sanitized.strip().rstrip(";")

    if not stripped.lower().startswith("select"):
        return "INVALID: query must start with SELECT."
    if FORBIDDEN_PATTERN.search(stripped):
        return "INVALID: query contains a forbidden write/DDL keyword. Read-only queries only."

    # Add a no-op OFFSET so a bare ORDER BY doesn't trip SQL Server's
    # "ORDER BY invalid in derived tables" rule once we wrap it below —
    # this validates the query as-written, it doesn't change what it does.
    to_wrap = stripped
    if _order_by_needs_offset(stripped):
        to_wrap = f"{stripped} OFFSET 0 ROWS"

    def _run(conn):
        with conn.cursor() as cur:
            # TOP 0 forces SQL Server/Fabric to plan and validate the query
            # (catches nonexistent tables/columns) without fetching real rows.
            cur.execute(f"SELECT TOP 0 * FROM ({to_wrap}) AS validation_check")

    try:
        run_with_connection(_run)
        return "VALID: query is well-formed and all referenced tables/columns exist."
    except Exception as e:
        return f"INVALID: {e}"