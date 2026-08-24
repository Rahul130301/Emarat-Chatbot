# tools/glossary.py
import os
import re
import time
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from openai import OpenAI
from embedding_utils import embed
from cosmos_catalog_db import get_container
from db import get_current_database
from azure.cosmos import exceptions as cosmos_exceptions
from dotenv import load_dotenv
load_dotenv(override=True)

chat_client = OpenAI(
    base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/v1",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
CHAT_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]

SEMANTIC_ACCEPT = 0.85
TOP_K = 5


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def llm_pick(entry_type: str, phrase: str, candidates: list[tuple[str, str]]) -> str | None:
    if not candidates:
        return None
    listing = "\n".join(f"- {term}: {definition}" for term, definition in candidates)
    prompt = (
        f"A user's question used the phrase: '{phrase}'.\n"
        f"Here are the defined {entry_type}s it might refer to:\n{listing}\n\n"
        "Which term (if any) does the phrase clearly refer to? Reply with ONLY the "
        "exact term text from the list above, or NONE if it doesn't clearly match any of them."
    )
    t0 = time.time()
    try:
        resp = chat_client.chat.completions.create(
            model=CHAT_DEPLOYMENT, messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        raise
    answer = resp.choices[0].message.content.strip()
    matches = [d for t, d in candidates if t == answer]
    return matches[0] if matches else None


def _lookup(entry_type: str, phrase: str) -> str:
    normalized = normalize(phrase)
    database = get_current_database()
    container = get_container("glossary_catalog")

    # 1. Exact — a direct point-read, not a query, since the migration keyed
    # every document's id as f"{entry_type}:{normalized_term}"
    try:
        item = container.read_item(item=f"{entry_type}:{normalized}", partition_key=database)
        return item["definition"]
    except cosmos_exceptions.CosmosResourceNotFoundError:
        pass

    # 2. Embedding — top-k via Cosmos vector search, scoped to this domain and entry_type
    query_vec = embed(phrase)
    results = list(container.query_items(
        query="""
            SELECT TOP @k c.term, c.definition, VectorDistance(c.embedding, @qv) AS score
            FROM c
            WHERE c.database = @db AND c.entry_type = @et
            ORDER BY VectorDistance(c.embedding, @qv)
        """,
        parameters=[
            {"name": "@k", "value": TOP_K},
            {"name": "@qv", "value": query_vec},
            {"name": "@db", "value": database},
            {"name": "@et", "value": entry_type},
        ],
        partition_key=database,
    ))

    if results and results[0]["score"] >= SEMANTIC_ACCEPT:  # verify direction — see note above
        return results[0]["definition"]

    # 3. LLM tiebreak — unchanged
    pool = [(r["term"], r["definition"]) for r in results]
    picked = llm_pick(entry_type, phrase, pool)
    if picked:
        return picked

    # 4. Genuinely undefined — unchanged
    return (
        f"No defined {entry_type} matches '{phrase}'. Don't invent an interpretation — "
        f"use the raw schema/column info instead, or ask the user to clarify."
    )


@tool(approval_mode="never_require")
def lookup_glossary_term(
    phrase: Annotated[str, Field(description="Business language from the user's question that might map to a specific table or column, e.g. 'revenue', 'client', 'deal size'.")],
) -> str:
    """Look up what a business term actually refers to in the database (which
    table/column). ALWAYS call this before assuming what a business word like
    'revenue' or 'client' maps to — never guess."""
    return _lookup("term", phrase)


@tool(approval_mode="never_require")
def lookup_metric(
    phrase: Annotated[str, Field(description="A named business metric from the user's question, e.g. 'total contract value', 'average deal size', 'renewal rate'.")],
) -> str:
    """Look up the exact, pre-approved SQL pattern for a named metric. ALWAYS
    call this before computing a metric yourself — use the returned pattern
    instead of inventing your own aggregate logic."""
    return _lookup("metric", phrase)