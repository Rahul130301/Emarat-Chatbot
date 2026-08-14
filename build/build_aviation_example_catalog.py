# build/build_aviation_example_catalog.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_catalog import get_aviation_catalog_connection
from embedding_utils import embed, embedding_to_json

EXAMPLES = [
    (
        "What is the total fuel volume uplifted across all flights?",
        "SELECT SUM(Volume) AS total_fuel_litres FROM [dbo].[aviation-uplifts];",
    ),
    (
        "Show fuel volume breakdown by airline.",
        "SELECT Airline, SUM(Volume) AS total_litres FROM [dbo].[aviation-uplifts] "
        "GROUP BY Airline ORDER BY total_litres DESC;",
    ),
    (
        "Which aircraft types consumed the most fuel volume?",
        "SELECT AircraftType, SUM(Volume) AS total_litres, COUNT(*) AS flight_count "
        "FROM [dbo].[aviation-uplifts] GROUP BY AircraftType ORDER BY total_litres DESC;",
    ),
    (
        "What is the fuel uplift volume and flight details for SkyMira Air?",
        "SELECT FlightNo, Registration, AircraftType, Stand, StartTime, EndTime, Volume, Date "
        "FROM [dbo].[aviation-uplifts] WHERE Airline = 'SkyMira Air';",
    ),
    (
        "Which stand handled the highest total fuel volume?",
        "SELECT Stand, SUM(Volume) AS total_litres, COUNT(*) AS flight_count "
        "FROM [dbo].[aviation-uplifts] GROUP BY Stand ORDER BY total_litres DESC;",
    ),
    (
        "List all flights on stand F29P.",
        "SELECT Airline, FlightNo, AircraftType, Registration, Volume, StartTime, EndTime, Date "
        "FROM [dbo].[aviation-uplifts] WHERE Stand = 'F29P';",
    ),
    (
        "What is the average fuel uplift volume for Boeing 787 aircraft?",
        "SELECT AVG(Volume) AS avg_volume_litres, COUNT(*) AS flight_count "
        "FROM [dbo].[aviation-uplifts] WHERE AircraftType = 'B787';",
    ),
    (
        "Show total fuel volume by airline for a bar chart.",
        "SELECT Airline, SUM(Volume) AS total_litres FROM [dbo].[aviation-uplifts] "
        "GROUP BY Airline ORDER BY total_litres DESC;",
    ),
]

def main():
    conn = get_aviation_catalog_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM example_sql_catalog")
    for question, sql in EXAMPLES:
        vec = embed(question)
        cur.execute(
            "INSERT INTO example_sql_catalog (question, sql, embedding) VALUES (?, ?, ?)",
            (question, sql, embedding_to_json(vec)),
        )
    conn.commit()
    conn.close()
    print(f"Indexed {len(EXAMPLES)} aviation example SQL pairs.")

if __name__ == "__main__":
    main()
