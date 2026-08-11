# tools/example_search.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_from_json
from similarity_utils import cosine_similarity

TOP_K = 3

@tool(approval_mode="never_require")
def search_example_sql(
    query: Annotated[str, Field(description="The user's question, used to find similar previously-solved questions and their correct SQL.")],
) -> str:
    conn = get_catalog_connection()
    cur = conn.cursor()
    cur.execute("SELECT question, sql, embedding FROM example_sql_catalog")
    rows = cur.fetchall()
    conn.close()

    query_vec = embed(query)
    scored = [
        (q, sql, cosine_similarity(query_vec, embedding_from_json(emb)))
        for q, sql, emb in rows if emb
    ]
    scored.sort(key=lambda r: r[2], reverse=True)
    top = scored[:TOP_K]
    if not top:
        return "No similar examples found."
    return "\n\n".join(f"Q: {q}\nSQL: {sql}" for q, sql, _ in top)