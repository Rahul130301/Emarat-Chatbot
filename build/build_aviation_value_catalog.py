# build/build_aviation_value_catalog.py
"""Builds/refreshes the categorical value catalog for aviation entity/value grounding.
Queries live Fabric warehouse 'aviation-warehouse' for distinct values."""
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_aviation_connection               # Fabric — source of real values
from db_catalog import get_aviation_catalog_connection  # SQLite — where the catalog lives
from embedding_utils import embed, embedding_to_json

# (table, column) pairs worth indexing for aviation entity resolution
CATALOG_COLUMNS = [
    ("aviation-uplifts", "Airline"),
    ("aviation-uplifts", "AircraftType"),
    ("aviation-uplifts", "Stand"),
    ("aviation-uplifts", "Location"),
    #("aviation-uplifts", "Registration"),
    #("aviation-uplifts", "FlightNo"),
]

# Fallback values from verified sample data if live connection is unavailable during offline build
FALLBACK_VALUES = {
    ("aviation-uplifts", "Airline"): [
        "NexaJet Airways", "AeroVanta", "SkyMira Air", "VeloAir International",
        "Orion Crest Airways", "Celestra Aviation", "NovaBridge Air",
        "Altiora Airways", "Meridian Skies", "Zenith Arrow",
        "AeroNova", "Solaris Air", "Apex Wings", "Horizon Jet",
        "QATAR AIRWAYS", "EMIRATES",
    ],
    ("aviation-uplifts", "AircraftType"): [
        "A320", "A321", "B737", "B737 MAX", "A330", "A340",
        "B767", "B787", "A350", "B777", "A380",
    ],
    ("aviation-uplifts", "Location"): [
        "DAP", "DCP", "T1", "T2", "T3", "INT", "DOM",
    ],
    ("aviation-uplifts", "Stand"): [
        "F29P", "A17P", "B42P", "C58P", "F18P", "B22P", "D11P", "C37P", "A09P"
    ],
    ("aviation-uplifts", "Registration"): [
        "H5JYA", "M1EDI", "J0KEO", "C2ZIZ", "M2BBG", "B9QKM", "W4IKF"
    ],
    ("aviation-uplifts", "FlightNo"): [
        "SM257", "ZA354", "SM319"
    ],
}

def normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def build_catalog(compute_embeddings: bool = True):
    catalog_conn = get_aviation_catalog_connection()
    cat_cur = catalog_conn.cursor()

    fabric_conn = None
    try:
        fabric_conn = get_aviation_connection()
    except Exception as e:
        print(f"Note: Could not connect to live Fabric ({e}). Using verified fallback seed values.")

    for table, column in CATALOG_COLUMNS:
        values = []
        if fabric_conn:
            try:
                with fabric_conn.cursor() as cur:
                    cur.execute(f"SELECT DISTINCT [{column}] FROM [dbo].[{table}] WHERE [{column}] IS NOT NULL")
                    values = [row[0] for row in cur.fetchall() if row[0] is not None]
            except Exception as e:
                print(f"Warning querying Fabric for {table}.{column}: {e}. Falling back to sample values.")
                values = FALLBACK_VALUES.get((table, column), [])
        else:
            values = FALLBACK_VALUES.get((table, column), [])

        # refresh semantics: clear this (table, column)'s old rows, reinsert fresh
        cat_cur.execute(
            "DELETE FROM value_catalog WHERE table_name = ? AND column_name = ?",
            (table, column),
        )
        for value in values:
            normalized = normalize(str(value))
            embedding_json = None
            if compute_embeddings:
                text = f"{column}: {value}"
                embedding_json = embedding_to_json(embed(text))
            cat_cur.execute(
                """INSERT INTO value_catalog
                   (table_name, column_name, canonical_value, normalized_value, embedding)
                   VALUES (?, ?, ?, ?, ?)""",
                (table, column, str(value), normalized, embedding_json),
            )
        print(f"Indexed {len(values)} distinct values from {table}.{column}")

    catalog_conn.commit()
    if fabric_conn:
        try:
            fabric_conn.close()
        except Exception:
            pass
    catalog_conn.close()

if __name__ == "__main__":
    build_catalog(compute_embeddings=True)
