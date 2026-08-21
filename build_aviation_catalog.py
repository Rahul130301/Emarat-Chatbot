# build_aviation_catalog.py
"""Master catalog builder for Aviation Operations & Uplift data warehouse.
Executes the modular build steps in the standard order matching Contracts & Sales:
1. init_aviation_catalog_db.py
2. build_aviation_value_catalog.py
3. build_aviation_glossary_catalog.py
4. build_aviation_example_catalog.py

Note: build_aviation_schema_catalog.py is no longer used (search_schema has been
retired in favor of search_schema_graph which uses the knowledge graph instead).
"""
import os
import sys

# Ensure root and build are in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build"))

from build import (
    init_aviation_catalog_db,
    build_aviation_value_catalog,
    build_aviation_glossary_catalog,
    build_aviation_example_catalog,
)

def main():
    print("=== Building Aviation Catalog (Matching Contracts & Sales Architecture) ===")
    print("[1/4] Initializing catalog schema...")
    init_aviation_catalog_db.init()

    print("[2/4] Building categorical value catalog from Fabric / seed data...")
    build_aviation_value_catalog.build_catalog(compute_embeddings=True)

    print("[3/4] Building glossary and metric catalog...")
    build_aviation_glossary_catalog.main()

    print("[4/4] Building example SQL catalog...")
    build_aviation_example_catalog.main()

    print("=== Aviation Catalog Built Successfully! ===")

if __name__ == "__main__":
    main()
