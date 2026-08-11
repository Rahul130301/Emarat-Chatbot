# tools/schema_search.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_from_json
from similarity_utils import cosine_similarity

TOP_K = 10

@tool(approval_mode="never_require")
def search_schema(
    query: Annotated[str, Field(description="The user's question, or a short paraphrase of what data is needed, used to semantically find the most relevant tables/columns.")],
) -> str:
    conn = get_catalog_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name, column_name, description, embedding FROM schema_catalog")
    rows = cur.fetchall()
    conn.close()

    query_vec = embed(query)
    scored = [
        (table, column, description, cosine_similarity(query_vec, embedding_from_json(emb)))
        for table, column, description, emb in rows if emb
    ]
    scored.sort(key=lambda r: r[3], reverse=True)
    top = scored[:TOP_K]
    if not top:
        return "No relevant schema entries found."
    return "\n".join(
        f"- {table}.{column or ''} (relevance {sim:.2f}): {description}"
        for table, column, description, sim in top
    )