# build/build_value_catalog.py
"""Builds/refreshes the categorical value catalog for entity/value grounding.
Re-run any time the underlying Fabric data changes."""
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_connection            # Fabric — source of real values
from db_catalog import get_catalog_connection  # SQLite — where the catalog lives
from embedding_utils import embed, embedding_to_json

# (table, column) pairs worth indexing for entity resolution
CATALOG_COLUMNS = [
    ("contracts", "company_name"),
    ("contracts", "industry"),
    ("contracts", "status"),
    ("contracts", "payment_terms"),
    ("contracts", "renewal_type"),
    ("sales", "product_or_service"),
    ("sales", "sales_region"),
]

def normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def build_catalog(compute_embeddings: bool = False):
    fabric_conn = get_connection()
    catalog_conn = get_catalog_connection()
    cat_cur = catalog_conn.cursor()

    with fabric_conn.cursor() as cur:
        for table, column in CATALOG_COLUMNS:
            cur.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
            values = [row[0] for row in cur.fetchall()]

            # refresh semantics: clear this (table, column)'s old rows, reinsert fresh
            cat_cur.execute(
                "DELETE FROM value_catalog WHERE table_name = ? AND column_name = ?",
                (table, column),
            )
            for value in values:
                normalized = normalize(str(value))
                embedding_json = None
                if compute_embeddings:
                    text = f"{column.replace('_', ' ')}: {value}"
                    embedding_json = embedding_to_json(embed(text))
                cat_cur.execute(
                    """INSERT INTO value_catalog
                       (table_name, column_name, canonical_value, normalized_value, embedding)
                       VALUES (?, ?, ?, ?, ?)""",
                    (table, column, str(value), normalized, embedding_json),
                )
            print(f"Indexed {len(values)} distinct values from {table}.{column}")

    catalog_conn.commit()
    fabric_conn.close()
    catalog_conn.close()

if __name__ == "__main__":
    build_catalog(compute_embeddings="--with-embeddings" in sys.argv)