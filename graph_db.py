# graph_db.py
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(override=True)

_driver = None

def get_driver():
    """Singleton Neo4j driver, shared across both the contracts and aviation
    agents. Domain separation is done with a `database` property on every
    node (contract-warehouse / aviation-warehouse), not separate instances —
    see build/build_knowledge_graph.py."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver

def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None