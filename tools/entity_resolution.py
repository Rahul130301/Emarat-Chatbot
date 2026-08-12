# tools/entity_resolution.py
import os
import re
import json
from pathlib import Path
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from openai import OpenAI
from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_from_json
from similarity_utils import fuzzy_ratio, cosine_similarity
from dotenv import load_dotenv
load_dotenv(override=True)

ALIASES_PATH = Path(__file__).parent / "aliases.json"

FUZZY_ACCEPT = 0.6
EMBED_ACCEPT = 0.90

chat_client = OpenAI(
    base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}/openai/v1",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)
CHAT_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


def normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_aliases() -> dict:
    return json.loads(ALIASES_PATH.read_text()) if ALIASES_PATH.exists() else {}


def lookup_alias(column_name: str, table_name: str | None, normalized: str) -> str | None:
    aliases = load_aliases()
    if table_name:
        scoped = aliases.get(f"{table_name}.{column_name}", {})
        if normalized in scoped:
            return scoped[normalized]
    return aliases.get(column_name, {}).get(normalized)


def llm_resolve(column_name: str, value: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    prompt = (
        f"A user referred to a '{column_name}' value as: '{value}'.\n"
        f"The only valid values in the database are: {candidates}.\n"
        "Which one did they most likely mean? Reply with ONLY the exact value from the "
        "list, or NONE if it's genuinely ambiguous or doesn't match any of them."
    )
    resp = chat_client.chat.completions.create(
        model=CHAT_DEPLOYMENT, messages=[{"role": "user", "content": prompt}],
    )
    answer = resp.choices[0].message.content.strip()
    return answer if answer in candidates else None


def _fetch_candidates(column_name: str, table_name: str | None) -> list[tuple]:
    """Returns (table_name, canonical_value, normalized_value, embedding_json) rows."""
    conn = get_catalog_connection()
    cur = conn.cursor()
    if table_name:
        cur.execute(
            "SELECT table_name, canonical_value, normalized_value, embedding "
            "FROM value_catalog WHERE column_name = ? AND table_name = ?",
            (column_name, table_name),
        )
    else:
        cur.execute(
            "SELECT table_name, canonical_value, normalized_value, embedding "
            "FROM value_catalog WHERE column_name = ?",
            (column_name,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


@tool(approval_mode="never_require")
def resolve_entity(
    column_name: Annotated[str, Field(description="Categorical column to resolve against: 'company_name', 'industry', 'status', 'payment_terms', 'renewal_type', 'product_or_service', or 'sales_region'.")],
    value: Annotated[str, Field(description="The raw value as the user typed or implied it, e.g. 'acme corp'.")],
    table_name: Annotated[str | None, Field(description="Which table this column belongs to, when it matters (e.g. 'status' could theoretically appear in multiple tables later). Optional.")] = None,
) -> str:
    """Resolve a raw user-typed value to the real canonical value(s) in the database.
    Tries exact match, then known alias, then fuzzy string match, then embedding
    similarity, then an LLM tiebreak — stopping at the first confident hit.
    ALWAYS call this before filtering on a categorical value."""
    normalized = normalize(value)
    rows = _fetch_candidates(column_name, table_name)
    if not rows:
        return f"No indexed values found for column '{column_name}'."

    # 1. Exact
    exact = [(t, cv) for t, cv, nv, _ in rows if nv == normalized]
    if exact:
        return _format("exact", 1.0, exact)

    # 2. Alias
    alias_target = lookup_alias(column_name, table_name, normalized)
    if alias_target:
        alias_hits = [(t, cv) for t, cv, nv, _ in rows if cv == alias_target]
        if alias_hits:
            return _format("alias", 0.98, alias_hits)

    # 3. Fuzzy
    fuzzy_scored = sorted(
        ((t, cv, fuzzy_ratio(nv, normalized)) for t, cv, nv, _ in rows),
        key=lambda r: r[2], reverse=True,
    )[:5]
    if fuzzy_scored and fuzzy_scored[0][2] >= FUZZY_ACCEPT:
        t, v, sim = fuzzy_scored[0]
        return _format("fuzzy", sim, [(t, v)])

    # 4. Embedding
    query_vec = embed(f"{column_name}: {value}")
    embed_scored = []
    for t, cv, nv, emb_json in rows:
        if emb_json:
            sim = cosine_similarity(query_vec, embedding_from_json(emb_json))
            embed_scored.append((t, cv, sim))
    embed_scored.sort(key=lambda r: r[2], reverse=True)
    embed_scored = embed_scored[:5]
    if embed_scored and embed_scored[0][2] >= EMBED_ACCEPT:
        t, v, sim = embed_scored[0]
        return _format("embedding", sim, [(t, v)])

    # 5. LLM tiebreak over merged candidate pool
    candidates = sorted({r[1] for r in fuzzy_scored} | {r[1] for r in embed_scored})
    llm_pick = llm_resolve(column_name, value, candidates)
    if llm_pick:
        rows_match = [(t, v) for t, v, _ in (fuzzy_scored + embed_scored) if v == llm_pick]
        return _format("llm", 0.75, rows_match)

    # 6. Nothing confident — surface candidates, don't guess
    if candidates:
        return (
            f"No confident match for '{value}' in {column_name}. "
            f"Closest candidates: {candidates}. Ask the user which one they meant."
        )
    return f"No match found for '{value}' in {column_name} — this value may not exist."


def _format(method: str, confidence: float, rows) -> str:
    values = sorted({r[1] for r in rows})
    tables = sorted({r[0] for r in rows})
    picked = values[0] if len(values) == 1 else values
    return f"Resolved to '{picked}' via {method} match (confidence {confidence:.2f}) in {tables}."
