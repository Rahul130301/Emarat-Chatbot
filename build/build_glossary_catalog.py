# build/build_glossary_catalog.py
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_to_json

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

TERMS = {
    "revenue": {
        "definition": "Dollar amount from sales transactions.",
        "maps_to_table": "sales", "maps_to_column": "revenue_amount", "synonym_of": None,
    },
    "sales": {
        "definition": "Same concept as revenue.",
        "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:revenue",
    },
    "deal size": {
        "definition": "Total value of a signed contract — not a single sale transaction.",
        "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None,
    },
    "contract worth": {
        "definition": "Same as deal size.",
        "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:deal size",
    },
    "client": {
        "definition": "A company with a contract and/or sales history. Not a separate table — "
                       "identified by company_name in contracts and sales.",
        "maps_to_table": "contracts", "maps_to_column": "company_name", "synonym_of": None,
    },
    "customer": {
        "definition": "Same as client.",
        "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:client",
    },
    "active contract": {
        "definition": "A contract where status = 'Active'.",
        "maps_to_table": "contracts", "maps_to_column": "status", "synonym_of": None,
    },
    "account manager": {
        "definition": "Internal owner of a contract.",
        "maps_to_table": "contracts", "maps_to_column": "contract_owner", "synonym_of": None,
    },
}

METRICS = {
    "total contract value": {
        "definition": "Sum of contract_value, typically filtered by status/industry/date as asked.",
        "formula_sql": "SELECT SUM(contract_value) FROM contracts",
        "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None,
    },
    "average deal size": {
        "definition": "Average contract_value across contracts matching the filter.",
        "formula_sql": "SELECT AVG(contract_value) FROM contracts",
        "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None,
    },
    "top clients": {
        "definition": "Companies ranked by total sales revenue. Default TOP 10 unless user specifies N.",
        "formula_sql": (
            "SELECT TOP 10 company_name, SUM(revenue_amount) AS total "
            "FROM sales GROUP BY company_name ORDER BY total DESC"
        ),
        "maps_to_table": "sales", "maps_to_column": "company_name", "synonym_of": None,
    },
    "contracts expiring soon": {
        "definition": "Active contracts with end_date within the next 90 days. Adjust window if user specifies one.",
        "formula_sql": (
            "SELECT * FROM contracts WHERE status = 'Active' "
            "AND end_date BETWEEN GETDATE() AND DATEADD(day, 90, GETDATE())"
        ),
        "maps_to_table": "contracts", "maps_to_column": "end_date", "synonym_of": None,
    },
    "renewal rate": {
        "definition": "Proportion of contracts with renewal_type = 'Auto-renew' among all contracts.",
        "formula_sql": (
            "SELECT 100.0 * SUM(CASE WHEN renewal_type = 'Auto-renew' THEN 1 ELSE 0 END) "
            "/ COUNT(*) FROM contracts"
        ),
        "maps_to_table": "contracts", "maps_to_column": "renewal_type", "synonym_of": None,
    },
}

def main():
    conn = get_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM glossary_catalog")
    for term, row in TERMS.items():
        vec = embed(f"{term}: {row['definition']}")
        cur.execute(
            """INSERT INTO glossary_catalog
               (term, normalized_term, definition, maps_to_table, maps_to_column, embedding)
               VALUES (?,?,?,?,?,?)""",
            (term, normalize(term), row["definition"], row.get("maps_to_table"),
             row.get("maps_to_column"), embedding_to_json(vec)),
        )
    for term, row in METRICS.items():
        vec = embed(f"{term}: {row['definition']}")
        cur.execute(
            """INSERT INTO glossary_catalog
               (entry_type, term, normalized_term, definition, maps_to_table, maps_to_column, embedding)
               VALUES (?,?,?,?,?,?,?)""",
            ("metric", term, normalize(term), row["definition"] + f" | SQL pattern: {row['formula_sql']}",
             row.get("maps_to_table"), row.get("maps_to_column"), embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(TERMS)} terms and {len(METRICS)} metrics.")

if __name__ == "__main__":
    main()