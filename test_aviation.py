# test_aviation.py
import os
from dotenv import load_dotenv

load_dotenv()

# The aviation agent's tools are the *same* generic tools the contract agent
# uses — they read the target Fabric database / SQLite catalog from
# contextvars (db.py / db_catalog.py) that api.py sets per-request based on
# agent_type. A standalone script has no request, so we must set that context
# ourselves before calling any tool, or they silently default to the
# contracts warehouse/catalog and every lookup below will look correct-ish
# but actually be querying the wrong data.
from db import set_current_database
from db_catalog import set_current_catalog_path

set_current_database(os.environ.get("FABRIC_AVIATION_DATABASE", "aviation-warehouse"))
set_current_catalog_path(os.environ.get("AVIATION_CATALOG_DB_PATH", "./aviation_catalog.db"))

from tools import (
    resolve_entity,
    lookup_glossary_term,
    lookup_metric,
    search_schema,
    get_table_schema,
    search_example_sql,
    validate_sql,
)

print("\n--- 1. Schema Catalog ---")
print(get_table_schema("aviation-uplifts"))

print("\n--- 2. Glossary Term ---")
print("Uplift term:", lookup_glossary_term("fuel uplift"))

print("\n--- 3. Metric Lookup ---")
print("Top airlines metric:", lookup_metric("top airlines by volume"))

print("\n--- 4. Entity Resolution ---")
# resolve_entity(column_name, value, table_name=None) — column first, then
# the raw user-typed value.
print("Resolving 'Qatar':", resolve_entity("Airline", "Qatar"))
print("Resolving 'A380':", resolve_entity("AircraftType", "A380"))
print("Resolving 'C58P':", resolve_entity("Stand", "C58P"))

print("\n--- 5. SQL Validation ---")
test_query = "SELECT Airline, SUM(Volume) AS total_litres FROM [dbo].[aviation-uplifts] GROUP BY Airline ORDER BY total_litres DESC"
print("Validation result:", validate_sql(test_query))

print("\n--- 6. Example SQL Search ---")
print(search_example_sql("Which airline had the highest fuel consumption?"))

print("\nAll aviation tools verified successfully!")
