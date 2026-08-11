# db_catalog.py
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

def get_catalog_connection():
    """Connection to the local SQLite catalog DB — value_catalog,
    glossary_catalog, schema_catalog, example_sql_catalog,
    document_chunks. This is agent infrastructure, not business data,
    so it doesn't need to live in Fabric."""
    return sqlite3.connect(os.environ.get("CATALOG_DB_PATH", "./catalog.db"))