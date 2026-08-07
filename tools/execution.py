# tools/execution.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_connection

@tool(approval_mode="never_require")
def run_sql(
    query: Annotated[str, Field(description="A validated, read-only SELECT query to execute — call this only after validate_sql has passed.")],
) -> str:
    if not query.strip().lower().startswith("select"):
        return "Error: only SELECT queries are allowed."
    conn = get_connection()
    conn.timeout = 5  # seconds — pyodbc's equivalent of statement_timeout
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
        return f"{colnames}\n" + "\n".join(str(tuple(r)) for r in rows[:50])
    except Exception as e:
        return f"SQL error: {e}"
    finally:
        conn.close()