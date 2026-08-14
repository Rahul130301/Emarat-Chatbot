import os
import sqlite3
from contextvars import ContextVar
from dotenv import load_dotenv

load_dotenv(override=True)

_current_catalog_path: ContextVar[str] = ContextVar(
    'current_catalog_path',
    default=os.environ.get("CATALOG_DB_PATH", "./catalog.db")
)

def set_current_catalog_path(path: str):
    """Set the local SQLite catalog path for the current async context."""
    _current_catalog_path.set(path)

def get_current_catalog_path() -> str:
    try:
        return _current_catalog_path.get()
    except LookupError:
        return os.environ.get("CATALOG_DB_PATH", "./catalog.db")

def get_catalog_connection():
    """Connection to the active local SQLite catalog DB (contracts or aviation)."""
    path = get_current_catalog_path()
    return sqlite3.connect(path)


def get_aviation_catalog_connection():
    """Connection to the local SQLite catalog DB for Aviation Agent."""
    return sqlite3.connect(os.environ.get("AVIATION_CATALOG_DB_PATH", "./aviation_catalog.db"))