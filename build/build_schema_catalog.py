# build/build_schema_catalog.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_to_json

SCHEMA = {
    ("contracts", None):
        "Commercial contracts with client companies. One row per contract. "
        "Contains contract value, dates, status, and renewal terms.",
    ("contracts", "contract_id"):
        "Primary key identifying a contract. Referenced by contract_documents.contract_id.",
    ("contracts", "company_name"):
        "Name of the client company the contract is with.",
    ("contracts", "industry"):
        "Industry sector of the client company.",
    ("contracts", "contract_value"):
        "Total dollar value of the contract. Use this for 'contract value', 'deal size', "
        "'worth', or 'how much is the contract for' questions.",
    ("contracts", "start_date"):
        "Date the contract took effect.",
    ("contracts", "end_date"):
        "Date the contract is scheduled to end (or ended, if expired/terminated).",
    ("contracts", "status"):
        "Contract status: Active, Expired, Under Renewal, or Terminated. "
        "'Current' or 'ongoing' contracts means status = 'Active'.",
    ("contracts", "contract_owner"):
        "Internal account manager responsible for the contract.",
    ("contracts", "payment_terms"):
        "Payment schedule, e.g. Net 30, Net 60, Quarterly.",
    ("contracts", "renewal_type"):
        "Whether the contract auto-renews, requires manual renewal, or is one-time. "
        "Use this column, not the document text, for a quick auto-renewal filter across "
        "many contracts — only fall back to the document for the specific clause wording.",

    ("sales", None):
        "Individual sales transactions with client companies. One row per sale. "
        "Independent of the contracts table — a company can appear in sales without "
        "an active contract row, and vice versa.",
    ("sales", "sale_id"):
        "Primary key identifying a sale transaction.",
    ("sales", "company_name"):
        "Name of the client company the sale was made to. Same naming as contracts.company_name.",
    ("sales", "sale_date"):
        "Date the sale occurred.",
    ("sales", "product_or_service"):
        "What was sold in this transaction.",
    ("sales", "revenue_amount"):
        "Dollar amount of this individual sale. Use this for 'revenue', 'sales', or "
        "'how much did we sell' questions — do NOT confuse with contracts.contract_value, "
        "which is the total value of a signed contract, not a transaction.",
    ("sales", "sales_region"):
        "Geographic region the sale was attributed to.",

    ("contract_documents", None):
        "Full contract document text in markdown, one row per document. Not used for "
        "numeric/aggregate SQL questions — use only when the question is about specific "
        "clause language (termination terms, liability, SLAs, etc).",
    ("contract_documents", "doc_id"):
        "Primary key identifying a contract document.",
    ("contract_documents", "contract_id"):
        "Foreign key referencing contracts.contract_id.",
    ("contract_documents", "document_name"):
        "Display name of the document.",
    ("contract_documents", "full_markdown"):
        "Full contract text in markdown. Large field — only fetch when a question needs "
        "actual clause content, never for structured/aggregate questions.",
}

def main():
    conn = get_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM schema_catalog")
    for (table, column), description in SCHEMA.items():
        vec = embed(f"{table}{'.' + column if column else ''}: {description}")
        cur.execute(
            "INSERT INTO schema_catalog (table_name, column_name, description, embedding) VALUES (?,?,?,?)",
            (table, column, description, embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(SCHEMA)} schema entries.")

if __name__ == "__main__":
    main()