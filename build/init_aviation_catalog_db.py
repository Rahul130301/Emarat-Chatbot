# build/init_aviation_catalog_db.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_aviation_catalog_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS value_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    embedding TEXT  -- JSON-encoded list of floats
);

CREATE TABLE IF NOT EXISTS glossary_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL DEFAULT 'term',
    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL,
    definition TEXT NOT NULL,
    maps_to_table TEXT,
    maps_to_column TEXT,
    embedding TEXT
);

CREATE TABLE IF NOT EXISTS schema_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    column_name TEXT,
    description TEXT NOT NULL,
    embedding TEXT
);

CREATE TABLE IF NOT EXISTS example_sql_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    embedding TEXT
);
"""

def init():
    conn = get_aviation_catalog_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print("aviation_catalog.db initialized.")

if __name__ == "__main__":
    init()
