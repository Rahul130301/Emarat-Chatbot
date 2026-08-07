# tools/document_lookup.py
from typing import Annotated
from pydantic import Field
from agent_framework import tool
from db import get_connection

@tool(approval_mode="never_require")
def get_contract_document(
    contract_id: Annotated[str, Field(description="Exact contract_id to fetch the full document for. If you only have a company name, resolve it to a contract_id first (via run_sql against the contracts table) before calling this.")],
) -> str:
    """Fetch the full markdown contract document for a given contract_id. Only
    call this when the question needs actual clause/document text (termination
    terms, liability, SLAs, etc) — never for numeric/aggregate questions, those
    go through run_sql against contracts/sales instead."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_name, full_markdown FROM contract_documents WHERE contract_id = ?",
                (contract_id,),
            )
            row = cur.fetchone()
        if not row:
            return f"No document found for contract_id '{contract_id}'."
        name, md = row
        return f"Document: {name}\n\n{md}"
    finally:
        conn.close()