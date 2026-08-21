# build/build_knowledge_graph.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_db import get_driver, close_driver
from embedding_utils import embed

import re

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

CONTRACT_TERMS = {
    "revenue": {"definition": "Dollar amount from sales transactions.", "maps_to_table": "sales", "maps_to_column": "revenue_amount", "synonym_of": None},
    "sales": {"definition": "Same concept as revenue.", "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:revenue"},
    "deal size": {"definition": "Total value of a signed contract — not a single sale transaction.", "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None},
    "contract worth": {"definition": "Same as deal size.", "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:deal size"},
    "client": {"definition": "A company with a contract and/or sales history. Not a separate table — identified by company_name in contracts and sales.", "maps_to_table": "contracts", "maps_to_column": "company_name", "synonym_of": None},
    "customer": {"definition": "Same as client.", "maps_to_table": None, "maps_to_column": None, "synonym_of": "term:client"},
    "active contract": {"definition": "A contract where status = 'Active'.", "maps_to_table": "contracts", "maps_to_column": "status", "synonym_of": None},
    "account manager": {"definition": "Internal owner of a contract.", "maps_to_table": "contracts", "maps_to_column": "contract_owner", "synonym_of": None},
}
CONTRACT_METRICS = {
    "total contract value": {"definition": "Sum of contract_value, typically filtered by status/industry/date as asked.", "formula_sql": "SELECT SUM(contract_value) FROM contracts", "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None},
    "average deal size": {"definition": "Average contract_value across contracts matching the filter.", "formula_sql": "SELECT AVG(contract_value) FROM contracts", "maps_to_table": "contracts", "maps_to_column": "contract_value", "synonym_of": None},
    "top clients": {"definition": "Companies ranked by total sales revenue. Default TOP 10 unless user specifies N.", "formula_sql": "SELECT TOP 10 company_name, SUM(revenue_amount) AS total FROM sales GROUP BY company_name ORDER BY total DESC", "maps_to_table": "sales", "maps_to_column": "company_name", "synonym_of": None},
    "contracts expiring soon": {"definition": "Active contracts with end_date within the next 90 days. Adjust window if user specifies one.", "formula_sql": "SELECT * FROM contracts WHERE status = 'Active' AND end_date BETWEEN GETDATE() AND DATEADD(day, 90, GETDATE())", "maps_to_table": "contracts", "maps_to_column": "end_date", "synonym_of": None},
    "renewal rate": {"definition": "Proportion of contracts with renewal_type = 'Auto-renew' among all contracts.", "formula_sql": "SELECT 100.0 * SUM(CASE WHEN renewal_type = 'Auto-renew' THEN 1 ELSE 0 END) / COUNT(*) FROM contracts", "maps_to_table": "contracts", "maps_to_column": "renewal_type", "synonym_of": None},
}

AVIATION_TERMS = {
    "fuel uplift": {"definition": "Fuel quantity in litres delivered into aircraft tanks.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None},
    "fuel volume": {"definition": "Same concept as fuel uplift, measured in Litres (L).", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "term:fuel uplift"},
    "uplift": {"definition": "Short for fuel uplift.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "term:fuel uplift"},
    "litres": {"definition": "Measurement unit for fuel volume.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None},
    "airline": {"definition": "Commercial carrier operating the flight.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": None},
    "carrier": {"definition": "Same concept as airline.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": "term:airline"},
    "aircraft": {"definition": "Aircraft fleet model or ICAO aircraft type.", "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": None},
    "fleet type": {"definition": "Same as aircraft type.", "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": "term:aircraft"},
    "plane model": {"definition": "Same as aircraft type.", "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": "term:aircraft"},
    "tail number": {"definition": "Aircraft tail registration code.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Registration", "synonym_of": None},
    "registration": {"definition": "Aircraft registration identifier.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Registration", "synonym_of": "term:tail number"},
    "flight": {"definition": "Flight number designation.", "maps_to_table": "aviation-uplifts", "maps_to_column": "FlightNo", "synonym_of": None},
    "flight number": {"definition": "Same as flight.", "maps_to_table": "aviation-uplifts", "maps_to_column": "FlightNo", "synonym_of": "term:flight"},
    "movement": {"definition": "Flight movement sequence identifier.", "maps_to_table": "aviation-uplifts", "maps_to_column": "MovementID", "synonym_of": None},
    "parking stand": {"definition": "Airport parking stand, gate, or bay.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": None},
    "stand": {"definition": "Airport fueling position or gate bay.", "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": "term:parking stand"},
    "airport location": {"definition": "Airport location code or terminal (e.g. DAP).", "maps_to_table": "aviation-uplifts", "maps_to_column": "Location", "synonym_of": None},
    "refueling duration": {"definition": "Duration of aircraft refueling in minutes.", "maps_to_table": "aviation-uplifts", "maps_to_column": "StartTime", "synonym_of": None},
}
AVIATION_METRICS = {
    "total fuel volume": {"definition": "Total sum of jet fuel uplifted in Litres across all matching flights.", "formula_sql": "SELECT SUM(Volume) AS total_fuel_litres FROM [dbo].[aviation-uplifts]", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None},
    "total uplift volume": {"definition": "Same as total fuel volume.", "formula_sql": "SELECT SUM(Volume) AS total_fuel_litres FROM [dbo].[aviation-uplifts]", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": "metric:total fuel volume"},
    "average fuel volume per flight": {"definition": "Average litres of jet fuel uplifted per flight movement.", "formula_sql": "SELECT AVG(Volume) AS avg_fuel_litres FROM [dbo].[aviation-uplifts]", "maps_to_table": "aviation-uplifts", "maps_to_column": "Volume", "synonym_of": None},
    "top airlines by volume": {"definition": "Airlines ranked by total fuel volume uplifted in Litres.", "formula_sql": "SELECT TOP 10 Airline, SUM(Volume) AS total_litres FROM [dbo].[aviation-uplifts] GROUP BY Airline ORDER BY total_litres DESC", "maps_to_table": "aviation-uplifts", "maps_to_column": "Airline", "synonym_of": None},
    "fuel volume by aircraft type": {"definition": "Fuel volume breakdown by aircraft fleet model.", "formula_sql": "SELECT AircraftType, SUM(Volume) AS total_litres, COUNT(*) AS flight_count FROM [dbo].[aviation-uplifts] GROUP BY AircraftType ORDER BY total_litres DESC", "maps_to_table": "aviation-uplifts", "maps_to_column": "AircraftType", "synonym_of": None},
    "busiest stands by volume": {"definition": "Airport parking stands ranked by total fuel volume uplifted.", "formula_sql": "SELECT TOP 10 Stand, COUNT(*) AS flight_count, SUM(Volume) AS total_litres FROM [dbo].[aviation-uplifts] GROUP BY Stand ORDER BY total_litres DESC", "maps_to_table": "aviation-uplifts", "maps_to_column": "Stand", "synonym_of": None},
    "total flight movements": {"definition": "Total count of flight refueling operations.", "formula_sql": "SELECT COUNT(*) AS total_movements FROM [dbo].[aviation-uplifts]", "maps_to_table": "aviation-uplifts", "maps_to_column": "MovementID", "synonym_of": None},
}

CONTRACT_SCHEMA = {
    ("contracts", None): "Commercial contracts with client companies. One row per contract. Contains contract value, dates, status, and renewal terms.",
    ("contracts", "contract_id"): "Primary key identifying a contract. Referenced by contract_documents.contract_id.",
    ("contracts", "company_name"): "Name of the client company the contract is with.",
    ("contracts", "industry"): "Industry sector of the client company.",
    ("contracts", "contract_value"): "Total dollar value of the contract. Use this for 'contract value', 'deal size', 'worth', or 'how much is the contract for' questions.",
    ("contracts", "start_date"): "Date the contract took effect.",
    ("contracts", "end_date"): "Date the contract is scheduled to end (or ended, if expired/terminated).",
    ("contracts", "status"): "Contract status: Active, Expired, Under Renewal, or Terminated. 'Current' or 'ongoing' contracts means status = 'Active'.",
    ("contracts", "contract_owner"): "Internal account manager responsible for the contract.",
    ("contracts", "payment_terms"): "Payment schedule, e.g. Net 30, Net 60, Quarterly.",
    ("contracts", "renewal_type"): "Whether the contract auto-renews, requires manual renewal, or is one-time. Use this column, not the document text, for a quick auto-renewal filter across many contracts — only fall back to the document for the specific clause wording.",
    ("sales", None): "Individual sales transactions with client companies. One row per sale. Independent of the contracts table — a company can appear in sales without an active contract row, and vice versa.",
    ("sales", "sale_id"): "Primary key identifying a sale transaction.",
    ("sales", "company_name"): "Name of the client company the sale was made to. Same naming as contracts.company_name.",
    ("sales", "sale_date"): "Date the sale occurred.",
    ("sales", "product_or_service"): "What was sold in this transaction.",
    ("sales", "revenue_amount"): "Dollar amount of this individual sale. Use this for 'revenue', 'sales', or 'how much did we sell' questions — do NOT confuse with contracts.contract_value, which is the total value of a signed contract, not a transaction.",
    ("sales", "sales_region"): "Geographic region the sale was attributed to.",
    ("contract_documents", None): "Full contract document text in markdown, one row per document. Not used for numeric/aggregate SQL questions — use only when the question is about specific clause language (termination terms, liability, SLAs, etc).",
    ("contract_documents", "doc_id"): "Primary key identifying a contract document.",
    ("contract_documents", "contract_id"): "Foreign key referencing contracts.contract_id.",
    ("contract_documents", "document_name"): "Display name of the document.",
    ("contract_documents", "full_markdown"): "Full contract text in markdown. Large field — only fetch when a question needs actual clause content, never for structured/aggregate questions.",
}
CONTRACT_RELATIONSHIPS = [
    ("contract_documents", "contracts", "contract_id", "many_to_one"),
    ("sales", "contracts", "contract_id", "many_to_one"),  
]

AVIATION_SCHEMA = {
    ("aviation-uplifts", None): "Aircraft refueling operations and fuel uplift transaction log in Microsoft Fabric [dbo].[aviation-uplifts]. One row per flight refueling operation. Tracks fuel volume in Litres (L), flight numbers, airlines, aircraft fleet models, stands, and turnaround timestamps.",
    ("aviation-uplifts", "RecordID"): "Primary key / unique identifier for each fueling operation or uplift transaction.",
    ("aviation-uplifts", "Airline"): "Commercial airline operator responsible for the flight (e.g. SkyMira Air, Zenith Arrow, AeroVanta, Orion Crest Airways, NovaBridge Air).",
    ("aviation-uplifts", "Date"): "Date of the flight movement and fueling operation.",
    ("aviation-uplifts", "MovementID"): "Airport movement sequence ID / identifier for the flight movement.",
    ("aviation-uplifts", "Location"): "Airport location code or terminal (e.g. DAP).",
    ("aviation-uplifts", "AircraftType"): "Aircraft fleet model / ICAO aircraft type (e.g. B787, A350, A380, B777, A340, A320, B737).",
    ("aviation-uplifts", "Registration"): "Aircraft tail registration number / tail code (e.g. H5JYA, M1EDI, J0KEO, C2ZIZ, M2BBG).",
    ("aviation-uplifts", "FlightNo"): "Flight number designation (e.g. SM257, ZA354, SM319).",
    ("aviation-uplifts", "StartTime"): "Start time of the aircraft refueling window (HH:MM).",
    ("aviation-uplifts", "EndTime"): "End time of the aircraft refueling window (HH:MM).",
    ("aviation-uplifts", "Stand"): "Airport parking stand, gate, or fueling bay position (e.g. F29P, A17P, B42P, C58P).",
    ("aviation-uplifts", "Volume"): "Quantity of jet fuel uplifted into the aircraft tanks, measured in Litres (L). Use this for 'fuel volume', 'uplift', 'consumption', 'how much fuel was pumped' questions.",
}
AVIATION_RELATIONSHIPS = []  # single flat table today — add here if that changes

DOMAINS = {
    "contract-warehouse": {
        "schema": CONTRACT_SCHEMA, "relationships": CONTRACT_RELATIONSHIPS,
        "terms": CONTRACT_TERMS, "metrics": CONTRACT_METRICS,
    },
    "aviation-warehouse": {
        "schema": AVIATION_SCHEMA, "relationships": AVIATION_RELATIONSHIPS,
        "terms": AVIATION_TERMS, "metrics": AVIATION_METRICS,
    },
}

def ensure_constraints(session):
    session.run("CREATE CONSTRAINT table_key IF NOT EXISTS FOR (t:Table) REQUIRE (t.name, t.database) IS UNIQUE")
    session.run("CREATE CONSTRAINT column_key IF NOT EXISTS FOR (c:Column) REQUIRE (c.name, c.table, c.database) IS UNIQUE")
    session.run("CREATE CONSTRAINT term_key IF NOT EXISTS FOR (b:BusinessTerm) REQUIRE (b.term, b.database) IS UNIQUE")

def build_glossary(session, db_name, terms, metrics):
    entries = {t: {**r, "entry_type": "term"} for t, r in terms.items()}
    entries.update({t: {**r, "entry_type": "metric"} for t, r in metrics.items()})

    # Pass 1: create every BusinessTerm node first (so synonym targets always exist)
    for term, row in entries.items():
        definition = row["definition"]
        if row.get("formula_sql"):
            definition = f"{definition} | SQL pattern: {row['formula_sql']}"
        session.run(
            """MERGE (b:BusinessTerm {term:$term, database:$db})
               SET b.normalized_term=$norm, b.definition=$def, b.entry_type=$et""",
            term=term, db=db_name, norm=normalize(term), def_=definition, et=row["entry_type"],
        ) if False else session.run(
            """MERGE (b:BusinessTerm {term:$term, database:$db})
               SET b.normalized_term=$norm, b.definition=$definition, b.entry_type=$entry_type""",
            term=term, db=db_name, norm=normalize(term), definition=definition, entry_type=row["entry_type"],
        )

    # Pass 2: MAPS_TO and SYNONYM_OF edges
    for term, row in entries.items():
        if row.get("maps_to_column"):
            session.run(
                """MATCH (b:BusinessTerm {term:$term, database:$db})
                   MATCH (c:Column {name:$col, table:$table, database:$db})
                   MERGE (b)-[:MAPS_TO]->(c)""",
                term=term, db=db_name, col=row["maps_to_column"], table=row["maps_to_table"],
            )
        elif row.get("maps_to_table"):
            session.run(
                """MATCH (b:BusinessTerm {term:$term, database:$db})
                   MATCH (t:Table {name:$table, database:$db})
                   MERGE (b)-[:MAPS_TO]->(t)""",
                term=term, db=db_name, table=row["maps_to_table"],
            )
        if row.get("synonym_of"):
            target = row["synonym_of"].split(":", 1)[1]
            session.run(
                """MATCH (a:BusinessTerm {term:$term, database:$db})
                   MATCH (b:BusinessTerm {term:$target, database:$db})
                   MERGE (a)-[:SYNONYM_OF]->(b)""",
                term=term, db=db_name, target=target,
            )
    print(f"[{db_name}] indexed {len(terms)} terms, {len(metrics)} metrics into graph.")

def main():
    driver = get_driver()
    with driver.session() as session:
        ensure_constraints(session)
        for db_name, content in DOMAINS.items():
            build_domain(session, db_name, content["schema"], content["relationships"])
            build_glossary(session, db_name, content["terms"], content["metrics"])
    close_driver()

def build_domain(session, db_name, schema, relationships):
    session.run("MERGE (:Database {name:$db})", db=db_name)

    for (table, column), description in schema.items():
        if column is None:
            vec = embed(f"{table}: {description}")
            session.run(
                """
                MATCH (d:Database {name:$db})
                MERGE (t:Table {name:$table, database:$db})
                SET t.description = $desc, t.embedding = $vec
                MERGE (d)-[:HAS_TABLE]->(t)
                """,
                db=db_name, table=table, desc=description, vec=vec,
            )
        else:
            session.run(
                """
                MATCH (t:Table {name:$table, database:$db})
                MERGE (c:Column {name:$col, table:$table, database:$db})
                SET c.description = $desc
                MERGE (t)-[:HAS_COLUMN]->(c)
                """,
                table=table, db=db_name, col=column, desc=description,
            )

    for many_table, one_table, via_column, cardinality in relationships:
        session.run(
            """
            MATCH (a:Table {name:$many_t, database:$db}), (b:Table {name:$one_t, database:$db})
            MERGE (a)-[r:REFERENCES {via_column:$via}]->(b)
            SET r.cardinality = $card
            """,
            many_t=many_table, one_t=one_table, via=via_column, db=db_name, card=cardinality,
        )

    print(f"[{db_name}] indexed {len(schema)} schema entries, {len(relationships)} relationships.")

if __name__ == "__main__":
    main()