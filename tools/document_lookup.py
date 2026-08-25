# tools/document_lookup.py
from typing import Annotated, Optional
from pydantic import Field
from agent_framework import tool
from cosmos_catalog_db import get_container
from embedding_utils import embed

TOP_K = 5

@tool(approval_mode="never_require")
def search_contract_clauses(
    query: Annotated[Optional[str], Field(description="What clause/topic to search for, e.g. 'termination notice period' or 'liability cap'. Omit only when full_document=True.")] = None,
    contract_id: Annotated[Optional[str], Field(description="Optional — restrict the search to one contract's document. Required when full_document=True. Omit otherwise to search across ALL contracts.")] = None,
    full_document: Annotated[bool, Field(description="Set True to retrieve every chunk of one contract's document in original order, for questions needing the whole document (e.g. 'summarize this contract'). Requires contract_id.")] = False,
) -> str:
    """Search over contract documents, split into clause/section-level chunks.
    Default mode: semantic search for a specific clause/topic — returns just
    the relevant section(s), fast and precise. Set full_document=True (with
    contract_id) only when the question genuinely needs the entire document,
    e.g. a full summary — that returns all chunks in reading order instead of
    a similarity-ranked subset."""
    container = get_container("contract_document_chunks")

    if full_document:
        if not contract_id:
            return "Error: full_document=True requires contract_id."
        results = container.query_items(
            query="SELECT c.contract_id, c.document_name, c.section_title, c.chunk_text, c.chunk_index "
                  "FROM c WHERE c.contract_id = @cid ORDER BY c.chunk_index",
            parameters=[{"name": "@cid", "value": contract_id}],
            partition_key=contract_id,
        )
        chunks = list(results)
        if not chunks:
            return f"No document found for contract_id '{contract_id}'."
        header = f"Document: {chunks[0]['document_name']} (contract_id={contract_id})"
        body = "\n\n".join(f"## {c['section_title']}\n{c['chunk_text']}" for c in chunks)
        return f"{header}\n\n{body}"

    if not query:
        return "Error: query is required unless full_document=True."

    query_vec = embed(query)
    base_query = (
        "SELECT TOP @k c.contract_id, c.document_name, c.section_title, c.chunk_text, "
        "VectorDistance(c.embedding, @qv) AS score FROM c "
    )
    if contract_id:
        results = container.query_items(
            query=base_query + "WHERE c.contract_id = @cid ORDER BY VectorDistance(c.embedding, @qv)",
            parameters=[{"name": "@k", "value": TOP_K}, {"name": "@qv", "value": query_vec},
                        {"name": "@cid", "value": contract_id}],
            partition_key=contract_id,
        )
    else:
        results = container.query_items(
            query=base_query + "ORDER BY VectorDistance(c.embedding, @qv)",
            parameters=[{"name": "@k", "value": TOP_K}, {"name": "@qv", "value": query_vec}],
            enable_cross_partition_query=True,
        )

    top = list(results)
    if not top:
        return "No matching clause/section found."
    return "\n\n---\n\n".join(
        f"[{r['contract_id']} — {r['document_name']} — {r['section_title']}]\n{r['chunk_text']}"
        for r in top
    )