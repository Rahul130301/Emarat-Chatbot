# tools/glossary.py
import os
import re
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from openai import AzureOpenAI
from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_from_json
from similarity_utils import cosine_similarity

chat_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
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
    resp = chat_client.chat.completions.create(
        model=CHAT_DEPLOYMENT, messages=[{"role": "user", "content": prompt}], temperature=0,
    )
    answer = resp.choices[0].message.content.strip()
    matches = [d for t, d in candidates if t == answer]
    return matches[0] if matches else None


def _lookup(entry_type: str, phrase: str) -> str:
    normalized = normalize(phrase)
    conn = get_catalog_connection()
    cur = conn.cursor()

    # 1. Exact
    cur.execute(
        "SELECT definition FROM glossary_catalog WHERE entry_type = ? AND normalized_term = ?",
        (entry_type, normalized),
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]

    # 2. Embedding — top-k candidates
    cur.execute(
        "SELECT term, definition, embedding FROM glossary_catalog WHERE entry_type = ?",
        (entry_type,),
    )
    all_rows = cur.fetchall()
    conn.close()

    query_vec = embed(phrase)
    scored = []
    for term, definition, emb_json in all_rows:
        if emb_json:
            sim = cosine_similarity(query_vec, embedding_from_json(emb_json))
            scored.append((term, definition, sim))
    scored.sort(key=lambda r: r[2], reverse=True)
    candidates = scored[:TOP_K]

    if candidates and candidates[0][2] >= SEMANTIC_ACCEPT:
        return candidates[0][1]

    # 3. LLM tiebreak
    pool = [(t, d) for t, d, _ in candidates]
    picked = llm_pick(entry_type, phrase, pool)
    if picked:
        return picked

    # 4. Genuinely undefined
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