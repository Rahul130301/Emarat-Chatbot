# build/migrate_catalogs_to_cosmos.py
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_catalog_connection, get_aviation_catalog_connection
from cosmos_catalog_db import get_container
import hashlib

SOURCES = {
    "contract-warehouse": get_catalog_connection,
    "aviation-warehouse": get_aviation_catalog_connection,
}

def migrate_value_catalog():
    container = get_container("value_catalog")
    total = 0
    for database, get_conn in SOURCES.items():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT table_name, column_name, canonical_value, normalized_value, embedding FROM value_catalog")
        rows = cur.fetchall()
        conn.close()

        for table_name, column_name, canonical_value, normalized_value, embedding_json in rows:
            if not embedding_json:
                continue  # skip rows never embedded
            doc = {
                "id": f"{table_name}:{column_name}:{normalized_value}",
                "database": database,
                "table_name": table_name,
                "column_name": column_name,
                "canonical_value": canonical_value,
                "normalized_value": normalized_value,
                "embedding": json.loads(embedding_json),
            }
            container.upsert_item(doc)
            total += 1
        print(f"[{database}] migrated {len(rows)} value_catalog rows.")
    print(f"Total value_catalog documents in Cosmos: {total}")


def migrate_glossary_catalog():
    container = get_container("glossary_catalog")
    total = 0
    for database, get_conn in SOURCES.items():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT entry_type, term, normalized_term, definition, embedding "
            "FROM glossary_catalog"
        )
        rows = cur.fetchall()
        conn.close()

        for entry_type, term, normalized_term, definition, embedding_json in rows:
            if not embedding_json:
                continue
            doc = {
                "id": f"{entry_type}:{normalized_term}",
                "database": database,
                "entry_type": entry_type,
                "term": term,
                "normalized_term": normalized_term,
                "definition": definition,
                "embedding": json.loads(embedding_json),
            }
            container.upsert_item(doc)
            total += 1
        print(f"[{database}] migrated {len(rows)} glossary_catalog rows.")
    print(f"Total glossary_catalog documents in Cosmos: {total}")


def migrate_example_sql_catalog():
    container = get_container("example_sql_catalog")
    total = 0
    for database, get_conn in SOURCES.items():
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT question, sql, embedding FROM example_sql_catalog")
        rows = cur.fetchall()
        conn.close()

        for question, sql, embedding_json in rows:
            if not embedding_json:
                continue
            doc_id = hashlib.sha1(f"{database}:{question}".encode()).hexdigest()
            doc = {
                "id": doc_id,
                "database": database,
                "question": question,
                "sql": sql,
                "embedding": json.loads(embedding_json),
            }
            container.upsert_item(doc)
            total += 1
        print(f"[{database}] migrated {len(rows)} example_sql_catalog rows.")
    print(f"Total example_sql_catalog documents in Cosmos: {total}")


if __name__ == "__main__":
    migrate_value_catalog()
    migrate_glossary_catalog()
    migrate_example_sql_catalog()