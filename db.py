# db.py
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """Connection to Fabric (business data: sales, contracts, contract_documents).
    Uses a service-principal identity that should be granted READ-ONLY
    permissions at the Fabric workspace/warehouse level — enforce this in
    Fabric itself, not just in application code."""
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={os.environ['FABRIC_SERVER']};"
        f"Database={os.environ['FABRIC_DATABASE']};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.environ['FABRIC_CLIENT_ID']};"
        f"PWD={os.environ['FABRIC_CLIENT_SECRET']};"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)