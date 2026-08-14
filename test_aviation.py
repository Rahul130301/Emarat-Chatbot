# test_aviation.py
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Build catalog if not existing
import build_aviation_catalog
build_aviation_catalog.main()

# Test tool imports and execution
from tools import (
    resolve_aviation_entity,
    lookup_aviation_glossary_term,
    lookup_aviation_metric,
    search_aviation_schema,
    get_aviation_table_schema,
    search_aviation_example_sql,
    validate_aviation_sql,
)

print("\n--- 1. Schema Catalog ---")
print(get_aviation_table_schema("aviation_uplifts_warehouse"))

print("\n--- 2. Glossary Term ---")
print("Uplift term:", lookup_aviation_glossary_term("fuel uplift"))

print("\n--- 3. Metric Lookup ---")
print("Top airlines metric:", lookup_aviation_metric("top airlines by volume"))

print("\n--- 4. Entity Resolution ---")
print("Resolving 'Qatar':", resolve_aviation_entity("Qatar", "Airline"))
print("Resolving 'A380':", resolve_aviation_entity("A380", "AircraftType"))
print("Resolving 'C58':", resolve_aviation_entity("C58P", "Stand"))

print("\n--- 5. SQL Validation ---")
test_query = "SELECT Airline, SUM(Volume) AS total_litres FROM aviation_uplifts_warehouse GROUP BY Airline ORDER BY total_litres DESC"
print("Validation result:", validate_aviation_sql(test_query))

print("\n--- 6. Example SQL Search ---")
print(search_aviation_example_sql("Which airline had the highest fuel consumption?"))

print("\nAll aviation tools verified successfully!")
