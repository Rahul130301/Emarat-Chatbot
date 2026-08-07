# build/build_example_catalog.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_to_json

EXAMPLES = [
    (
        "How many active contracts do we have?",
        "SELECT COUNT(*) FROM contracts WHERE status = 'Active';",
    ),
    (
        "What's the total contract value for the healthcare industry?",
        "SELECT SUM(contract_value) FROM contracts WHERE industry = 'Healthcare';",
    ),
    (
        "Show me the top 5 clients by revenue.",
        "SELECT TOP 5 company_name, SUM(revenue_amount) AS total_revenue "
        "FROM sales GROUP BY company_name ORDER BY total_revenue DESC;",
    ),
    (
        "Which contracts are expiring in the next 90 days?",
        "SELECT contract_id, company_name, end_date FROM contracts "
        "WHERE status = 'Active' AND end_date BETWEEN GETDATE() AND DATEADD(day, 90, GETDATE());",
    ),
    (
        "What's the average deal size for Acme Corp?",
        # demonstrates: entity resolution (company_name) + glossary metric (avg deal size)
        "SELECT AVG(contract_value) FROM contracts WHERE company_name = 'Acme Corp';",
    ),
    (
        "How many contracts auto-renew?",
        "SELECT COUNT(*) FROM contracts WHERE renewal_type = 'Auto-renew';",
    ),
    (
        "List sales by region for last quarter.",
        "SELECT sales_region, SUM(revenue_amount) AS total "
        "FROM sales WHERE sale_date >= DATEADD(quarter, -1, GETDATE()) "
        "GROUP BY sales_region ORDER BY total DESC;",
    ),
]

def main():
    conn = get_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM example_sql_catalog")
    for question, sql in EXAMPLES:
        vec = embed(question)
        cur.execute(
            "INSERT INTO example_sql_catalog (question, sql, embedding) VALUES (?, ?, ?)",
            (question, sql, embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(EXAMPLES)} example SQL pairs.")

if __name__ == "__main__":
    main()