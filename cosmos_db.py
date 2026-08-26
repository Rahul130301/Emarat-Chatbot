import os
import time
import uuid
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions
from dotenv import load_dotenv

load_dotenv(override=True)

COSMOS_URL = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
DATABASE_NAME = "chat_history_db"

_client: CosmosClient = None
_database = None
_sessions_container = None
_messages_container = None


async def init_cosmos():
    """Initialize Cosmos DB client and ensure database and containers exist."""
    global _client, _database, _sessions_container, _messages_container
    if not COSMOS_URL or not COSMOS_KEY:
        print("Warning: Cosmos DB credentials not found. Set COSMOS_ENDPOINT and COSMOS_KEY in .env")
        return

    _client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY)

    try:
        # Create database if it doesn't exist
        _database = await _client.create_database_if_not_exists(id=DATABASE_NAME)

        # Create sessions container (partitioned by user_id)
        # Note: offer_throughput is omitted for serverless Cosmos DB accounts
        _sessions_container = await _database.create_container_if_not_exists(
            id="sessions",
            partition_key=PartitionKey(path="/user_id")
        )

        # Create messages container (partitioned by session_id)
        _messages_container = await _database.create_container_if_not_exists(
            id="messages",
            partition_key=PartitionKey(path="/session_id")
        )
        print(f"Cosmos DB initialized successfully: {DATABASE_NAME}")
    except exceptions.CosmosHttpResponseError as e:
        print(f"Failed to initialize Cosmos DB: {e.message}")


async def close_cosmos():
    """Close the Cosmos DB client connection."""
    global _client
    if _client:
        await _client.close()


AGENT_KEY_NAMES = {
    "contracts-fast": "Contracts Agent — Fast",
    "contracts-reasoning": "Contracts Agent — Reasoning",
    "aviation-fast": "Aviation Agent — Fast",
    "aviation-reasoning": "Aviation Agent — Reasoning",
}


async def create_session(user_id: str, title: str = "New Chat", agent_key: str = "contracts-fast") -> str:
    """Create a new chat session in Cosmos DB. Returns the session_id."""
    if not _sessions_container:
        # Cosmos DB not available — fall back to a plain UUID
        return str(uuid.uuid4())

    session_id = str(uuid.uuid4())
    session_item = {
        "id": session_id,
        "user_id": user_id,
        "title": title,
        "agent_key": agent_key,
        "agent_name": AGENT_KEY_NAMES.get(agent_key, agent_key),
        "updatedAt": int(time.time() * 1000)
    }
    await _sessions_container.create_item(body=session_item)
    return session_id


async def get_user_sessions(user_id: str, agent_key: str = None) -> list:
    """Return sessions for a user, newest first. Optionally filter by agent_key."""
    if not _sessions_container:
        return []

    if agent_key:
        query = (
            "SELECT * FROM c WHERE c.user_id = @user_id "
            "AND c.agent_key = @agent_key ORDER BY c.updatedAt DESC"
        )
        parameters = [
            {"name": "@user_id",   "value": user_id},
            {"name": "@agent_key", "value": agent_key},
        ]
    else:
        query = "SELECT * FROM c WHERE c.user_id = @user_id ORDER BY c.updatedAt DESC"
        parameters = [{"name": "@user_id", "value": user_id}]

    items = _sessions_container.query_items(
        query=query,
        parameters=parameters
    )
    return [item async for item in items]


async def update_session_title(session_id: str, user_id: str, title: str):
    """Update the display title for a session."""
    if not _sessions_container:
        return

    try:
        item = await _sessions_container.read_item(item=session_id, partition_key=user_id)
        item["title"] = title
        item["updatedAt"] = int(time.time() * 1000)
        await _sessions_container.replace_item(item=session_id, body=item)
    except exceptions.CosmosResourceNotFoundError:
        pass


async def update_session_agent(session_id: str, user_id: str, agent_key: str):
    """Retarget an unused (empty) session to a different agent."""
    if not _sessions_container:
        return

    try:
        item = await _sessions_container.read_item(item=session_id, partition_key=user_id)
        item["agent_key"] = agent_key
        item["agent_name"] = AGENT_KEY_NAMES.get(agent_key, agent_key)
        item["updatedAt"] = int(time.time() * 1000)
        await _sessions_container.replace_item(item=session_id, body=item)
    except exceptions.CosmosResourceNotFoundError:
        pass


async def save_message(
    session_id: str,
    role: str,
    content: str,
    user_id: str = None,
    agent_key: str = None,
    agent_type: str = "contracts",
    tool_calls: list = None,
    mode: str = None
) -> str:
    """Save a chat message to the messages container with full isolation tags."""
    if not _messages_container:
        return str(uuid.uuid4())

    message_id = str(uuid.uuid4())
    message_item = {
        "id": message_id,
        "session_id": session_id,
        "role": role,           # 'user' or 'assistant'
        "content": content,
        "agent_type": agent_type,
        "timestamp": int(time.time() * 1000)
    }

    if user_id:
        message_item["user_id"] = user_id
    if agent_key:
        message_item["agent_key"] = agent_key
    if tool_calls:
        message_item["toolCalls"] = tool_calls
    if mode:
        message_item["mode"] = mode

    await _messages_container.create_item(body=message_item)
    return message_id


async def get_session_messages(session_id: str, user_id: str = None, agent_key: str = None) -> list:
    """Return all messages for a session, securely checking ownership if provided."""
    if not _messages_container:
        return []

    # Build query securely checking all required bounds
    query = "SELECT * FROM c WHERE c.session_id = @session_id"
    parameters = [{"name": "@session_id", "value": session_id}]

    if user_id:
        query += " AND c.user_id = @user_id"
        parameters.append({"name": "@user_id", "value": user_id})
        
    if agent_key:
        query += " AND (NOT IS_DEFINED(c.agent_key) OR c.agent_key = @agent_key)"
        parameters.append({"name": "@agent_key", "value": agent_key})

    query += " ORDER BY c.timestamp ASC"

    items = _messages_container.query_items(
        query=query,
        parameters=parameters
    )
    return [item async for item in items]


async def delete_session(session_id: str, user_id: str):
    """Delete a session and all its messages from Cosmos DB."""
    # Delete all messages for this session first
    if _messages_container:
        try:
            query = "SELECT c.id FROM c WHERE c.session_id = @session_id"
            parameters = [{"name": "@session_id", "value": session_id}]
            items = _messages_container.query_items(query=query, parameters=parameters)
            async for item in items:
                await _messages_container.delete_item(item=item["id"], partition_key=session_id)
        except Exception as e:
            print(f"Warning: Could not delete messages for session {session_id}: {e}")

    # Delete the session itself
    if _sessions_container:
        try:
            await _sessions_container.delete_item(item=session_id, partition_key=user_id)
        except Exception as e:
            print(f"Warning: Could not delete session {session_id}: {e}")
