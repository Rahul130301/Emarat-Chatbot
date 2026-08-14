import os
import pyodbc
from contextvars import ContextVar
from dotenv import load_dotenv

load_dotenv(override=True)

_current_database: ContextVar[str] = ContextVar(
    'current_database',
    default=os.environ.get('FABRIC_DATABASE', 'contract-warehouse')
)

def set_current_database(db_name: str):
    """Set the target Fabric warehouse database for the current async context."""
    _current_database.set(db_name)

def get_current_database() -> str:
    try:
        return _current_database.get()
    except LookupError:
        return os.environ.get('FABRIC_DATABASE', 'contract-warehouse')

def get_connection(database: str | None = None):
    """Connection to Fabric warehouse (contract-warehouse or aviation-warehouse)."""
    db_name = database or get_current_database()
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={os.environ['FABRIC_SERVER']};"
        f"Database={db_name};"
        "Authentication=ActiveDirectoryServicePrincipal;"
        f"UID={os.environ['FABRIC_CLIENT_ID']};"
        f"PWD={os.environ['FABRIC_CLIENT_SECRET']};"
        "Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


def get_aviation_connection():
    """Connection to Fabric Aviation Data Warehouse (aviation-warehouse)."""
    aviation_db = os.environ.get('FABRIC_AVIATION_DATABASE', 'aviation-warehouse')
    return get_connection(database=aviation_db)