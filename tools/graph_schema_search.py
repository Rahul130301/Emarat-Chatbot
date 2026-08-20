# tools/graph_schema_search.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_current_database
from graph_db import get_driver
from embedding_utils import embed
from similarity_utils import cosine_similarity

TOP_TABLES = 3

def _closest_tables(query_vec, database):
    with get_driver().session() as session:
        rows = session.run(
            "MATCH (t:Table {database:$db}) WHERE t.embedding IS NOT NULL "
            "RETURN t.name AS name, t.description AS description, t.embedding AS embedding",
            db=database,
        )
        scored = [(r["name"], r["description"], cosine_similarity(query_vec, r["embedding"])) for r in rows]
    scored.sort(key=lambda r: r[2], reverse=True)
    return scored[:TOP_TABLES]

@tool(approval_mode="never_require")
def search_schema_graph(
    query: Annotated[str, Field(description="The user's question, or a short paraphrase of what data is needed, used to semantically find the most relevant tables/columns and how they join.")],
) -> str:
    database = get_current_database()
    top_tables = _closest_tables(embed(query), database)
    if not top_tables:
        return "No relevant schema entries found."

    blocks = []
    with get_driver().session() as session:
        for table_name, table_desc, sim in top_tables:
            row = session.run(
                """
                MATCH (t:Table {name:$table, database:$db})
                OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
                OPTIONAL MATCH (t)-[r:REFERENCES]-(related:Table)
                RETURN collect(DISTINCT c.name + ': ' + c.description) AS columns,
                       collect(DISTINCT related.name + ' (via ' + coalesce(r.via_column,'') + ', ' + coalesce(r.join_type,'') + ')') AS joinable
                """,
                table=table_name, db=database,
            ).single()
            columns = [c for c in row["columns"] if c]
            joinable = [j for j in row["joinable"] if j]
            block = [f"TABLE {table_name} (relevance {sim:.2f}): {table_desc}"]
            if columns:
                block.append("  Columns:\n    - " + "\n    - ".join(columns))
            if joinable:
                block.append("  Joinable tables:\n    - " + "\n    - ".join(joinable))
            blocks.append("\n".join(block))
    return "\n\n".join(blocks)