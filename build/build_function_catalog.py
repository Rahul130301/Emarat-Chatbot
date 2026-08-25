# build/build_function_catalog.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cosmos_catalog_db import get_container
from embedding_utils import embed
from query_functions import REGISTRY

def build():
    container = get_container("function_catalog")
    for database, functions in REGISTRY.items():
        for name, func in functions.items():
            doc = {
                "id": name,
                "database": database,
                "function_name": name,
                "description": func.description,
                "parameters": func.parameters,
                "embedding": embed(f"{name}: {func.description}"),
            }
            container.upsert_item(doc)
        print(f"[{database}] indexed {len(functions)} query functions into Cosmos.")

if __name__ == "__main__":
    build()