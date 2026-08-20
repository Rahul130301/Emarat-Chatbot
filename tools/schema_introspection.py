# tools/schema_introspection.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import run_with_connection

@tool(approval_mode="never_require")
def list_tables() -> str:
    """List all table names available in the database."""
    def _run(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.name AS schema_name, t.name AS table_name
                FROM sys.tables t
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                ORDER BY s.name, t.name
                """
            )
            return cur.fetchall()

    rows = run_with_connection(_run)
    return "\n".join(f"{schema}.{table}" for schema, table in rows)

@tool(approval_mode="never_require")
def get_table_schema(
    table_name: Annotated[str, Field(description="Exact table name to inspect, as returned by list_tables or search_schema_graph.")],
) -> str:
    """Return the exact column names and data types for a given table. Call this
    after search_schema_graph has narrowed down which table(s) are relevant — never
    guess a column name."""
    def _run(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.name AS column_name, ty.name AS data_type
                FROM sys.columns c
                JOIN sys.tables t ON c.object_id = t.object_id
                JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                WHERE t.name = ?
                ORDER BY c.column_id
                """,
                (table_name,),
            )
            return cur.fetchall()

    rows = run_with_connection(_run)
    if not rows:
        return f"No table named '{table_name}' found."
    return "\n".join(f"{col} ({dtype})" for col, dtype in rows)