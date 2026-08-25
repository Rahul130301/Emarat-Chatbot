# tools/function_search.py
import json
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_current_database
from cosmos_catalog_db import get_container
from embedding_utils import embed
from tools.glossary import llm_pick

SEMANTIC_ACCEPT = 0.80
TOP_K = 5

@tool(approval_mode="never_require")
def find_query_function(
    question: Annotated[str, Field(description="The user's question, as asked or lightly paraphrased.")],
) -> str:
    """Check whether this question matches a pre-built, pre-approved query
    function before doing anything else. ALWAYS call this FIRST, before
    lookup_glossary_term, lookup_metric, or search_schema_graph. If it
    returns a function_name, resolve any entity parameters with
    resolve_entity, then call run_query_function — do not write SQL, do not
    call search_schema_graph/validate_sql/run_sql for this question. If it
    says no function matches, proceed to the normal pipeline."""
    database = get_current_database()
    container = get_container("function_catalog")
    query_vec = embed(question)

    results = list(container.query_items(
        query="""
            SELECT TOP @k c.function_name, c.description, c.parameters,
                   VectorDistance(c.embedding, @qv) AS score
            FROM c
            WHERE c.database = @db
            ORDER BY VectorDistance(c.embedding, @qv)
        """,
        parameters=[
            {"name": "@k", "value": TOP_K},
            {"name": "@qv", "value": query_vec},
            {"name": "@db", "value": database},
        ],
        partition_key=database,
    ))

    if not results:
        return "No query functions defined for this domain."

    if results[0]["score"] >= SEMANTIC_ACCEPT:
        top = results[0]
    else:
        candidates = [(r["function_name"], r["description"]) for r in results]
        picked_desc = llm_pick("query function", question, candidates)
        if not picked_desc:
            return "No pre-built function matches this question. Proceed with the normal schema/SQL pipeline."
        top = next(r for r in results if r["description"] == picked_desc)

    params = top["parameters"]
    param_list = ", ".join(f"{k}{'*' if v.get('required') else ''}" for k, v in params.items())
    return (f"Matched function: {top['function_name']} — {top['description']}\n"
            f"Parameters ({param_list}; * = required): {json.dumps(params)}\n"
            f"Resolve any entity values with resolve_entity, then call run_query_function "
            f"with function_name='{top['function_name']}'.")