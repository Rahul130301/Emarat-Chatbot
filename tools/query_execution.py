# tools/query_execution.py
from typing import Annotated, Optional
from pydantic import Field
from agent_framework import tool
from db import get_current_database, run_with_connection
from query_functions import get_function

MAX_ROWS = 200


@tool(approval_mode="never_require")
def run_query_function(
    function_name: Annotated[str, Field(description="The exact function_name returned by lookup_metric.")],
    parameters: Annotated[Optional[dict], Field(description="Parameter values as a JSON object, using the exact parameter names lookup_metric listed. Omit any optional parameter you're not filtering on.")] = None,
) -> str:
    """Run a pre-built, pre-approved query function instead of writing raw SQL.
    Use this whenever lookup_metric points you to a function_name — the SQL is
    fixed and already reviewed, so there's no risk of an incorrect join or
    aggregation; only your filter values vary. Do not call search_schema_graph,
    validate_sql, or run_sql for a question this handles."""
    parameters = parameters or {}
    database = get_current_database()
    func = get_function(database, function_name)
    if func is None:
        return (f"Error: no query function named '{function_name}' exists for this domain. "
                 f"Call lookup_metric again to confirm the correct function_name, or fall back "
                 f"to search_schema_graph and writing SQL yourself if no function applies.")

    errors = []
    for pname, spec in func.parameters.items():
        if spec.get("required") and pname not in parameters:
            errors.append(f"missing required parameter '{pname}' ({spec.get('description', '')})")
    for pname, value in parameters.items():
        if pname not in func.parameters:
            errors.append(f"unknown parameter '{pname}' — valid parameters: {list(func.parameters.keys())}")
            continue
        allowed = func.parameters[pname].get("allowed_values")
        if allowed and value not in allowed:
            errors.append(f"'{pname}' must be one of {allowed}, got '{value}'")
    if errors:
        return "Error: " + "; ".join(errors)

    try:
        sql, values = func.build(parameters)
    except Exception as e:
        return f"Error building query: {e}"

    def _run(conn):
        with conn.cursor() as cur:
            cur.execute(sql, values)
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
        return colnames, rows

    try:
        colnames, rows = run_with_connection(_run)
    except Exception as e:
        return f"SQL error: {e}"

    shown = rows[:MAX_ROWS]
    header = f"ROWS RETURNED: {len(shown)}"
    if len(rows) > len(shown):
        header += f" (truncated from {len(rows)})"
    body = "\n".join(str(tuple(r)) for r in shown)
    return f"{header}\n{colnames}\n{body}"