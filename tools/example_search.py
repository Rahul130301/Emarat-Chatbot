# tools/example_search.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from cosmos_catalog_db import get_container
from embedding_utils import embed
from db import get_current_database

TOP_K = 3

@tool(approval_mode="never_require")
def search_example_sql(
    query: Annotated[str, Field(description="The user's question, used to find similar previously-solved questions and their correct SQL.")],
) -> str:
    container = get_container("example_sql_catalog")
    database = get_current_database()
    query_vec = embed(query)

    results = container.query_items(
        query="""
            SELECT TOP @k c.question, c.sql, VectorDistance(c.embedding, @qv) AS distance
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
    )
    top = list(results)
    if not top:
        return "No similar examples found."
    return "\n\n".join(f"Q: {r['question']}\nSQL: {r['sql']}" for r in top)