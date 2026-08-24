# build/build_function_catalog.py
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_catalog_connection, get_aviation_catalog_connection
from embedding_utils import embed, embedding_to_json
from query_functions import REGISTRY

CATALOG_CONNECTIONS = {
    "contract-warehouse": get_catalog_connection,
    "aviation-warehouse": get_aviation_catalog_connection,
}

def build():
    for database, functions in REGISTRY.items():
        conn = CATALOG_CONNECTIONS[database]()
        cur = conn.cursor()
        cur.execute("DELETE FROM function_catalog")
        for name, func in functions.items():
            text = f"{name}: {func.description}"
            embedding_json = embedding_to_json(embed(text))
            params_json = json.dumps(func.parameters)
            cur.execute(
                """INSERT INTO function_catalog
                   (function_name, description, parameters_json, embedding)
                   VALUES (?, ?, ?, ?)""",
                (name, func.description, params_json, embedding_json),
            )
        conn.commit()
        conn.close()
        print(f"[{database}] indexed {len(functions)} query functions.")

if __name__ == "__main__":
    build()