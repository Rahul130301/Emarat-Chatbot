# tools/validation.py
import re
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_connection

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

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # TOP 0 forces SQL Server/Fabric to plan and validate the query
            # (catches nonexistent tables/columns) without fetching real rows.
            cur.execute(f"SELECT TOP 0 * FROM ({stripped}) AS validation_check")
        return "VALID: query is well-formed and all referenced tables/columns exist."
    except Exception as e:
        return f"INVALID: {e}"
    finally:
        conn.close()