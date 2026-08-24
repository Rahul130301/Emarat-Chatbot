# tools/function_search.py
import json
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_current_database
from db_catalog import get_catalog_connection, get_aviation_catalog_connection
from embedding_utils import embed, embedding_from_json
from similarity_utils import cosine_similarity
from tools.glossary import llm_pick  # reuse the same LLM-tiebreak helper

SEMANTIC_ACCEPT = 0.80
TOP_K = 5

CATALOG_CONNECTIONS = {
    "contract-warehouse": get_catalog_connection,
    "aviation-warehouse": get_aviation_catalog_connection,
}


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
    conn = CATALOG_CONNECTIONS[database]()
    cur = conn.cursor()
    cur.execute("SELECT function_name, description, parameters_json, embedding FROM function_catalog")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "No query functions defined for this domain."

    query_vec = embed(question)
    scored = []
    for name, desc, params_json, emb_json in rows:
        sim = cosine_similarity(query_vec, embedding_from_json(emb_json))
        scored.append((name, desc, params_json, sim))
    scored.sort(key=lambda r: r[3], reverse=True)

    top = scored[0]
    if top[3] >= SEMANTIC_ACCEPT:
        matched_name, matched_desc, matched_params_json = top[0], top[1], top[2]
    else:
        candidates = [(n, d) for n, d, _, _ in scored[:TOP_K]]
        picked_desc = llm_pick("query function", question, candidates)
        if not picked_desc:
            return "No pre-built function matches this question. Proceed with the normal schema/SQL pipeline."
        match = next((n, d, p) for n, d, p, _ in scored if d == picked_desc)
        matched_name, matched_desc, matched_params_json = match

    params = json.loads(matched_params_json)
    param_list = ", ".join(f"{k}{'*' if v.get('required') else ''}" for k, v in params.items())
    return (f"Matched function: {matched_name} — {matched_desc}\n"
            f"Parameters ({param_list}; * = required): {matched_params_json}\n"
            f"Resolve any entity values with resolve_entity, then call run_query_function "
            f"with function_name='{matched_name}'.")