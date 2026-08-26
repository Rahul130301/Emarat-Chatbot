"""
Shared in-memory session store.
Both api.py and auth_azure.py import from here to avoid circular imports.
Cosmos DB persists message history; this dict caches live LLM agent objects.
"""

sessions: dict = {}
SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds

def make_session_entry(username: str, display_name: str = "", email: str = "") -> dict:
    """Create a blank in-memory session entry for a user."""
    import time
    return {
        "username": username,
        "display_name": display_name or username,
        "email": email,
        "obj_contracts_reasoning": None,
        "obj_contracts_fast": None,
        "obj_aviation_reasoning": None,
        "obj_aviation_fast": None,
        "last_active": time.time(),
    }
