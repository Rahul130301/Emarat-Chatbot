# build/create_cosmos_containers.py
"""One-time setup: creates the three catalog containers with vector search
enabled. Safe to re-run (create_container_if_not_exists is idempotent), but
note: once a container's vector policy is set, it can't be changed — if you
ever need a different EMBEDDING_DIMENSIONS, you'd need a new container."""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.cosmos import PartitionKey
from cosmos_catalog_db import get_cosmos_database

EMBEDDING_DIMENSIONS = 3072

def _vector_policy():
    return {
        "vectorEmbeddings": [
            {"path": "/embedding", "dataType": "float32",
             "distanceFunction": "cosine", "dimensions": EMBEDDING_DIMENSIONS}
        ]
    }

def _indexing_policy():
    return {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": "/embedding/*"}, {"path": "/\"_etag\"/?"}],
        "vectorIndexes": [{"path": "/embedding", "type": "quantizedFlat"}],
    }

CONTAINERS = ["value_catalog", "glossary_catalog", "example_sql_catalog", "function_catalog"]

def main():
    db = get_cosmos_database()
    for name in CONTAINERS:
        db.create_container_if_not_exists(
            id=name,
            partition_key=PartitionKey(path="/database"),
            indexing_policy=_indexing_policy(),
            vector_embedding_policy=_vector_policy(),
        )
        print(f"Container '{name}' ready.")

if __name__ == "__main__":
    main()