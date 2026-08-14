# build/build_aviation_schema_catalog.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_aviation_catalog_connection
from embedding_utils import embed, embedding_to_json

SCHEMA = {
    ("aviation-uplifts", None):
        "Aircraft refueling operations and fuel uplift transaction log in Microsoft Fabric [dbo].[aviation-uplifts]. "
        "One row per flight refueling operation. Tracks fuel volume in Litres (L), flight numbers, airlines, "
        "aircraft fleet models, stands, and turnaround timestamps.",
    ("aviation-uplifts", "RecordID"):
        "Primary key / unique identifier for each fueling operation or uplift transaction.",
    ("aviation-uplifts", "Airline"):
        "Commercial airline operator responsible for the flight (e.g. SkyMira Air, Zenith Arrow, AeroVanta, "
        "Orion Crest Airways, NovaBridge Air).",
    ("aviation-uplifts", "Date"):
        "Date of the flight movement and fueling operation.",
    ("aviation-uplifts", "MovementID"):
        "Airport movement sequence ID / identifier for the flight movement.",
    ("aviation-uplifts", "Location"):
        "Airport location code or terminal (e.g. DAP).",
    ("aviation-uplifts", "AircraftType"):
        "Aircraft fleet model / ICAO aircraft type (e.g. B787, A350, A380, B777, A340, A320, B737).",
    ("aviation-uplifts", "Registration"):
        "Aircraft tail registration number / tail code (e.g. H5JYA, M1EDI, J0KEO, C2ZIZ, M2BBG).",
    ("aviation-uplifts", "FlightNo"):
        "Flight number designation (e.g. SM257, ZA354, SM319).",
    ("aviation-uplifts", "StartTime"):
        "Start time of the aircraft refueling window (HH:MM).",
    ("aviation-uplifts", "EndTime"):
        "End time of the aircraft refueling window (HH:MM).",
    ("aviation-uplifts", "Stand"):
        "Airport parking stand, gate, or fueling bay position (e.g. F29P, A17P, B42P, C58P).",
    ("aviation-uplifts", "Volume"):
        "Quantity of jet fuel uplifted into the aircraft tanks, measured in Litres (L). "
        "Use this for 'fuel volume', 'uplift', 'consumption', 'how much fuel was pumped' questions.",
}

def main():
    conn = get_aviation_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM schema_catalog")
    for (table, column), description in SCHEMA.items():
        vec = embed(f"{table}{'.' + column if column else ''}: {description}")
        cur.execute(
            "INSERT INTO schema_catalog (table_name, column_name, description, embedding) VALUES (?,?,?,?)",
            (table, column, description, embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(SCHEMA)} aviation schema entries.")

if __name__ == "__main__":
    main()
