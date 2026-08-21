# build/build_value_catalog.py
"""Builds/refreshes the categorical value catalog for entity/value grounding.
Incremental by default: only embeds values that are new since the last run,
and removes catalog entries for values no longer present in Fabric (renamed/
deleted). Pass --full to force a full rebuild (re-embeds everything) if you
ever suspect the catalog has drifted in a way incremental sync won't fix."""
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_connection
from db_catalog import get_catalog_connection
from embedding_utils import embed, embedding_to_json

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

def build_catalog(compute_embeddings: bool = False, full_rebuild: bool = False):
    fabric_conn = get_connection()
    catalog_conn = get_catalog_connection()
    cat_cur = catalog_conn.cursor()

    with fabric_conn.cursor() as cur:
        for table, column in CATALOG_COLUMNS:
            cur.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
            live_values = [row[0] for row in cur.fetchall()]
            live_by_normalized = {normalize(str(v)): str(v) for v in live_values}

            if full_rebuild:
                cat_cur.execute(
                    "DELETE FROM value_catalog WHERE table_name = ? AND column_name = ?",
                    (table, column),
                )
                existing_normalized = set()
            else:
                cat_cur.execute(
                    "SELECT normalized_value FROM value_catalog WHERE table_name = ? AND column_name = ?",
                    (table, column),
                )
                existing_normalized = {row[0] for row in cat_cur.fetchall()}

            to_add = {n: v for n, v in live_by_normalized.items() if n not in existing_normalized}
            to_remove = existing_normalized - set(live_by_normalized.keys())

            if to_remove:
                cat_cur.executemany(
                    "DELETE FROM value_catalog WHERE table_name = ? AND column_name = ? AND normalized_value = ?",
                    [(table, column, n) for n in to_remove],
                )

            for normalized, value in to_add.items():
                embedding_json = None
                if compute_embeddings:
                    text = f"{column.replace('_', ' ')}: {value}"
                    embedding_json = embedding_to_json(embed(text))
                cat_cur.execute(
                    """INSERT INTO value_catalog
                       (table_name, column_name, canonical_value, normalized_value, embedding)
                       VALUES (?, ?, ?, ?, ?)""",
                    (table, column, value, normalized, embedding_json),
                )

            print(f"{table}.{column}: +{len(to_add)} new, -{len(to_remove)} stale, "
                  f"{len(live_values)} total live values.")

    catalog_conn.commit()
    fabric_conn.close()
    catalog_conn.close()

if __name__ == "__main__":
    build_catalog(
        compute_embeddings="--with-embeddings" in sys.argv,
        full_rebuild="--full" in sys.argv,
    )