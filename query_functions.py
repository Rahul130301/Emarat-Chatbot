# query_functions.py
"""Pre-built, parameterized SQL 'functions' for common questions. The SQL
skeleton is fixed and reviewed once; only filter VALUES vary, and those are
always passed as bound parameters (pyodbc ? placeholders), never string-
interpolated. This is why this path skips validate_sql/check_ontology
entirely — there's no way for a filter value to change the query's
structure, so the class of bug those checks exist for can't occur here."""


class QueryFunction:
    def __init__(self, name, description, parameters, build):
        self.name = name
        self.description = description
        self.parameters = parameters  # dict: param_name -> spec
        self.build = build            # callable(params: dict) -> (sql: str, values: list)


def _add_filter(conditions, values, column, value, op="="):
    if value is not None:
        conditions.append(f"{column} {op} ?")
        values.append(value)


# ---------------------------------------------------------------------
# CONTRACT DOMAIN
# ---------------------------------------------------------------------

def _build_total_contract_value(p):
    conditions, values = [], []
    _add_filter(conditions, values, "status", p.get("status"))
    _add_filter(conditions, values, "industry", p.get("industry"))
    if p.get("date_from"):
        conditions.append("start_date >= ?"); values.append(p["date_from"])
    if p.get("date_to"):
        conditions.append("start_date <= ?"); values.append(p["date_to"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (f"SELECT SUM(contract_value) AS total_contract_value, "
           f"COUNT(*) AS contract_count FROM contracts {where}")
    return sql, values

total_contract_value = QueryFunction(
    name="total_contract_value",
    description="Total contract_value across contracts, optionally filtered by status, industry, and/or date range.",
    parameters={
        "status": {"required": False, "type": "string", "allowed_values": ["Active", "Expired", "Under Renewal", "Terminated"], "description": "Filter to a specific contract status."},
        "industry": {"required": False, "type": "string", "description": "Filter to a specific industry."},
        "date_from": {"required": False, "type": "string", "description": "Only contracts starting on/after this date (YYYY-MM-DD)."},
        "date_to": {"required": False, "type": "string", "description": "Only contracts starting on/before this date (YYYY-MM-DD)."},
    },
    build=_build_total_contract_value,
)


def _build_compare_clients(p):
    names = p.get("company_names") or []
    if not names:
        raise ValueError("company_names must be a non-empty list.")
    placeholders = ", ".join(["?"] * len(names))
    sql = (f"SELECT c.company_name, SUM(c.contract_value) AS total_contract_value, "
           f"COUNT(DISTINCT c.contract_id) AS contract_count, "
           f"COALESCE(sv.total_sales, 0) AS total_sales_revenue "
           f"FROM contracts c "
           f"LEFT JOIN (SELECT contract_id, SUM(revenue_amount) AS total_sales "
           f"           FROM sales GROUP BY contract_id) sv ON sv.contract_id = c.contract_id "
           f"WHERE c.company_name IN ({placeholders}) "
           f"GROUP BY c.company_name")
    return sql, names

compare_clients = QueryFunction(
    name="compare_clients",
    description="Compare two or more named companies side by side on contract value, contract count, and total sales revenue.",
    parameters={
        "company_names": {"required": True, "type": "list[string]", "description": "The exact, resolved company names to compare (use resolve_entity first)."},
    },
    build=_build_compare_clients,
)


# ---------------------------------------------------------------------
# AVIATION DOMAIN
# ---------------------------------------------------------------------

def _build_total_fuel_volume(p):
    conditions, values = [], []
    _add_filter(conditions, values, "Airline", p.get("airline"))
    _add_filter(conditions, values, "AircraftType", p.get("aircraft_type"))
    if p.get("date_from"):
        conditions.append("Date >= ?"); values.append(p["date_from"])
    if p.get("date_to"):
        conditions.append("Date <= ?"); values.append(p["date_to"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (f"SELECT SUM(Volume) AS total_fuel_litres, COUNT(*) AS flight_count "
           f"FROM [dbo].[aviation-uplifts] {where}")
    return sql, values

total_fuel_volume = QueryFunction(
    name="total_fuel_volume",
    description="Total jet fuel volume (Litres) uplifted, optionally filtered by airline, aircraft type, and/or date range.",
    parameters={
        "airline": {"required": False, "type": "string", "description": "Filter to a specific airline (use resolve_entity first)."},
        "aircraft_type": {"required": False, "type": "string", "description": "Filter to a specific aircraft fleet type."},
        "date_from": {"required": False, "type": "string", "description": "Only flights on/after this date (YYYY-MM-DD)."},
        "date_to": {"required": False, "type": "string", "description": "Only flights on/before this date (YYYY-MM-DD)."},
    },
    build=_build_total_fuel_volume,
)


def _build_compare_airlines(p):
    names = p.get("airline_names") or []
    if not names:
        raise ValueError("airline_names must be a non-empty list.")
    placeholders = ", ".join(["?"] * len(names))
    sql = (f"SELECT Airline, SUM(Volume) AS total_fuel_litres, COUNT(*) AS flight_count, "
           f"AVG(Volume) AS avg_fuel_litres_per_flight "
           f"FROM [dbo].[aviation-uplifts] "
           f"WHERE Airline IN ({placeholders}) "
           f"GROUP BY Airline")
    return sql, names

compare_airlines = QueryFunction(
    name="compare_airlines",
    description="Compare two or more named airlines side by side on total fuel volume, flight count, and average fuel volume per flight.",
    parameters={
        "airline_names": {"required": True, "type": "list[string]", "description": "The exact, resolved airline names to compare (use resolve_entity first)."},
    },
    build=_build_compare_airlines,
)


# ---------------------------------------------------------------------
# REGISTRY — extend by adding more QueryFunction entries above and here
# ---------------------------------------------------------------------

REGISTRY = {
    "contract-warehouse": {
        "total_contract_value": total_contract_value,
        "compare_clients": compare_clients,
    },
    "aviation-warehouse": {
        "total_fuel_volume": total_fuel_volume,
        "compare_airlines": compare_airlines,
    },
}


def get_function(database: str, name: str) -> QueryFunction | None:
    return REGISTRY.get(database, {}).get(name)


def list_functions(database: str) -> list[QueryFunction]:
    return list(REGISTRY.get(database, {}).values())