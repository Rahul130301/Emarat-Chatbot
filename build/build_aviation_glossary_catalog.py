# build/build_aviation_glossary_catalog.py
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_aviation_catalog_connection
from embedding_utils import embed, embedding_to_json

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

TERMS = {
    "fuel uplift": {
        "definition": "Fuel quantity in litres delivered into aircraft tanks.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None,
    },
    "fuel volume": {
        "definition": "Same concept as fuel uplift, measured in Litres (L).",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "term:fuel uplift",
    },
    "uplift": {
        "definition": "Short for fuel uplift.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "term:fuel uplift",
    },
    "litres": {
        "definition": "Measurement unit for fuel volume.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None,
    },
    "airline": {
        "definition": "Commercial carrier operating the flight.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": None,
    },
    "carrier": {
        "definition": "Same concept as airline.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": "term:airline",
    },
    "aircraft": {
        "definition": "Aircraft fleet model or ICAO aircraft type.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": None,
    },
    "fleet type": {
        "definition": "Same as aircraft type.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": "term:aircraft",
    },
    "plane model": {
        "definition": "Same as aircraft type.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": "term:aircraft",
    },
    "tail number": {
        "definition": "Aircraft tail registration code.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Registration", "synonym_of": None,
    },
    "registration": {
        "definition": "Aircraft registration identifier.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Registration", "synonym_of": "term:tail number",
    },
    "flight": {
        "definition": "Flight number designation.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "FlightNo", "synonym_of": None,
    },
    "flight number": {
        "definition": "Same as flight.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "FlightNo", "synonym_of": "term:flight",
    },
    "movement": {
        "definition": "Flight movement sequence identifier.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "MovementID", "synonym_of": None,
    },
    "parking stand": {
        "definition": "Airport parking stand, gate, or bay.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": None,
    },
    "stand": {
        "definition": "Airport fueling position or gate bay.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": "term:parking stand",
    },
    "airport location": {
        "definition": "Airport location code or terminal (e.g. DAP).",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Location", "synonym_of": None,
    },
    "refueling duration": {
        "definition": "Duration of aircraft refueling in minutes.",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "StartTime", "synonym_of": None,
    },
}

METRICS = {
    "total fuel volume": {
        "definition": "Total sum of jet fuel uplifted in Litres across all matching flights.",
        "formula_sql": "SELECT SUM(Volume) AS total_fuel_litres FROM [dbo].[aviation-uplifts]",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None,
    },
    "total uplift volume": {
        "definition": "Same as total fuel volume.",
        "formula_sql": "SELECT SUM(Volume) AS total_fuel_litres FROM [dbo].[aviation-uplifts]",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "metric:total fuel volume",
    },
    "average fuel volume per flight": {
        "definition": "Average litres of jet fuel uplifted per flight movement.",
        "formula_sql": "SELECT AVG(Volume) AS avg_fuel_litres FROM [dbo].[aviation-uplifts]",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None,
    },
    "top airlines by volume": {
        "definition": "Airlines ranked by total fuel volume uplifted in Litres.",
        "formula_sql": (
            "SELECT TOP 10 Airline, SUM(Volume) AS total_litres "
            "FROM [dbo].[aviation-uplifts] GROUP BY Airline ORDER BY total_litres DESC"
        ),
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": None,
    },
    "fuel volume by aircraft type": {
        "definition": "Fuel volume breakdown by aircraft fleet model.",
        "formula_sql": (
            "SELECT AircraftType, SUM(Volume) AS total_litres, COUNT(*) AS flight_count "
            "FROM [dbo].[aviation-uplifts] GROUP BY AircraftType ORDER BY total_litres DESC"
        ),
        "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": None,
    },
    "busiest stands by volume": {
        "definition": "Airport parking stands ranked by total fuel volume uplifted.",
        "formula_sql": (
            "SELECT TOP 10 Stand, COUNT(*) AS flight_count, SUM(Volume) AS total_litres "
            "FROM [dbo].[aviation-uplifts] GROUP BY Stand ORDER BY total_litres DESC"
        ),
        "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": None,
    },
    "total flight movements": {
        "definition": "Total count of flight refueling operations.",
        "formula_sql": "SELECT COUNT(*) AS total_movements FROM [dbo].[aviation-uplifts]",
        "maps_to_table": "aviation-uplifts", "maps_to_column": "MovementID", "synonym_of": None,
    },
}

def main():
    conn = get_aviation_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM glossary_catalog")
    for term, row in TERMS.items():
        vec = embed(f"{term}: {row['definition']}")
        cur.execute(
            """INSERT INTO glossary_catalog
               (term, normalized_term, definition, maps_to_table, maps_to_column, embedding)
               VALUES (?,?,?,?,?,?)""",
            (term, normalize(term), row["definition"], row.get("maps_to_table"),
             row.get("maps_to_column"), embedding_to_json(vec)),
        )
    for term, row in METRICS.items():
        vec = embed(f"{term}: {row['definition']}")
        cur.execute(
            """INSERT INTO glossary_catalog
               (entry_type, term, normalized_term, definition, maps_to_table, maps_to_column, embedding)
               VALUES (?,?,?,?,?,?,?)""",
            ("metric", term, normalize(term), row["definition"] + f" | SQL pattern: {row['formula_sql']}",
             row.get("maps_to_table"), row.get("maps_to_column"), embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(TERMS)} aviation terms and {len(METRICS)} metrics.")

if __name__ == "__main__":
    main()
