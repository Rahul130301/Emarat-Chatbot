from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import threading
import time
import uuid
import sys
import os

# Ensure the current directory is in sys.path so we can import from agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import set_current_database, warmup_connections
from db_catalog import set_current_catalog_path
from agent import build_reasoning_agent as build_contracts_reasoning_agent, build_fast_agent as build_contracts_fast_agent
from aviation_agent import build_aviation_reasoning_agent, build_aviation_fast_agent
from agent_framework._harness._todo import TodoSessionStore
import cosmos_db
from scope_gate import check_gate
from session_store import sessions, SESSION_TIMEOUT, make_session_entry
from auth_azure import router as auth_router


contracts_reasoning_agent = None
contracts_fast_agent = None
aviation_reasoning_agent = None
aviation_fast_agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Warm up DB connections in the background
    threading.Thread(target=warmup_connections, name="db-warmup", daemon=True).start()

    # Connect to Cosmos DB (creates containers if they don't exist)
    await cosmos_db.init_cosmos()

    # Build agents
    global contracts_reasoning_agent, contracts_fast_agent
    global aviation_reasoning_agent, aviation_fast_agent

    try:
        contracts_reasoning_agent = build_contracts_reasoning_agent()
    except Exception as e:
        print(f"Warning: Could not build contracts reasoning agent on startup: {e}")
        contracts_reasoning_agent = None

    try:
        contracts_fast_agent = build_contracts_fast_agent()
    except Exception as e:
        print(f"Warning: Could not build contracts fast agent on startup: {e}")
        contracts_fast_agent = None

    try:
        aviation_reasoning_agent = build_aviation_reasoning_agent()
    except Exception as e:
        print(f"Warning: Could not build aviation reasoning agent on startup: {e}")
        aviation_reasoning_agent = None

    try:
        aviation_fast_agent = build_aviation_fast_agent()
    except Exception as e:
        print(f"Warning: Could not build aviation fast agent on startup: {e}")
        aviation_fast_agent = None

    yield

    # --- Shutdown ---
    await cosmos_db.close_cosmos()


app = FastAPI(lifespan=lifespan)

# Mount SSO authentication router
app.include_router(auth_router)

# Allow CORS for the frontend
# NOTE: allow_origins must list exact origins (not "*") when allow_credentials=True
# so that the browser will send the session cookie cross-origin.
_FRONTEND_ORIGIN = os.environ.get("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store lives in session_store.py (shared with auth_azure.py)
# sessions = {}  ← imported from session_store


class ChatRequest(BaseModel):
    message: str
    session_id: str
    agent_type: str = "contracts"  # "contracts" or "aviation"
    agent_key: str | None = None   # "contracts-fast" | "contracts-reasoning" | "aviation-fast" | "aviation-reasoning"


@app.post("/logout")
async def logout(req: Request):
    """Legacy logout — clears the in-memory session.
    For SSO sessions, the frontend should call POST /api/v1/auth/logout instead."""
    auth_header = req.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_id = auth_header.split(" ")[1]
        if session_id in sessions:
            del sessions[session_id]
            return {"status": "logged_out"}
    return {"status": "ok"}


@app.get("/sessions")
async def get_sessions(username: str, agent_key: str = None):
    """Return past sessions for this user from Cosmos DB, optionally filtered by agent_key."""
    return await cosmos_db.get_user_sessions(user_id=username, agent_key=agent_key)


class NewSessionRequest(BaseModel):
    username: str
    title: str = "New Chat"
    agent_key: str = "contracts-fast"


@app.post("/sessions")
async def create_new_session(req: NewSessionRequest):
    """Create a new chat session in Cosmos DB and register it in memory."""
    session_id = await cosmos_db.create_session(
        user_id=req.username,
        title=req.title,
        agent_key=req.agent_key
    )
    sessions[session_id] = {
        "username": req.username,
        "agent_key": req.agent_key,
        "obj_contracts_reasoning": None,
        "obj_contracts_fast": None,
        "obj_aviation_reasoning": None,
        "obj_aviation_fast": None,
        "last_active": time.time(),
    }
    return {"session_id": session_id}


class UpdateSessionAgentRequest(BaseModel):
    username: str
    agent_key: str


@app.patch("/sessions/{session_id}/agent")
async def update_session_agent(session_id: str, req: UpdateSessionAgentRequest):
    """Point an unused New Chat at a different agent without creating another tab."""
    await cosmos_db.update_session_agent(session_id, req.username, req.agent_key)
    if session_id in sessions:
        sessions[session_id]["agent_key"] = req.agent_key
    return {"status": "ok"}


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, username: str = None, agent_key: str = None):
    """Return all messages for a given session from Cosmos DB, verifying ownership."""
    return await cosmos_db.get_session_messages(
        session_id=session_id,
        user_id=username,
        agent_key=agent_key
    )


class RegisterSessionRequest(BaseModel):
    username: str
    session_id: str


@app.post("/sessions/register")
async def register_session(req: RegisterSessionRequest):
    """Register an existing Cosmos DB session into the in-memory store.
    Called when a returning user logs in and resumes their most recent session.
    """
    if req.session_id not in sessions:
        sessions[req.session_id] = {
            "username": req.username,
            "obj_contracts_reasoning": None,
            "obj_contracts_fast": None,
            "obj_aviation_reasoning": None,
            "obj_aviation_fast": None,
            "last_active": time.time(),
        }
    else:
        sessions[req.session_id]["last_active"] = time.time()
    return {"status": "ok"}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, username: str):
    """Delete a session and all its messages from Cosmos DB."""
    # Remove from in-memory store
    if session_id in sessions:
        del sessions[session_id]
    # Remove from Cosmos DB
    await cosmos_db.delete_session(session_id=session_id, user_id=username)
    return {"status": "deleted"}



def _get_session_data(session_id: str):
    if session_id not in sessions:
        # Session not in memory (e.g., server restarted) — recreate wrapper
        sessions[session_id] = {
            "username": "unknown",
            "obj_contracts_reasoning": None,
            "obj_contracts_fast": None,
            "obj_aviation_reasoning": None,
            "obj_aviation_fast": None,
            "last_active": time.time(),
        }
    session_data = sessions[session_id]
    if time.time() - session_data["last_active"] > SESSION_TIMEOUT:
        del sessions[session_id]
        raise HTTPException(status_code=401, detail="Session expired")
    session_data["last_active"] = time.time()
    return session_data


def _get_session_obj(session_data: dict, agent, obj_key: str):
    """Lazily create (and cache) the per-agent session object."""
    if session_data[obj_key] is None and agent is not None:
        session_data[obj_key] = agent.create_session()
    return session_data[obj_key]


async def _stream_chat(agent, session_obj, session_id: str, message: str, is_harness: bool, agent_type: str = "contracts", agent_key: str = None):
    """Shared SSE generator. Saves user + assistant messages to Cosmos DB around the stream."""
    if agent_type == "aviation":
        set_current_database(os.environ.get("FABRIC_AVIATION_DATABASE", "aviation-warehouse"))
        set_current_catalog_path(os.environ.get("AVIATION_CATALOG_DB_PATH", "./aviation_catalog.db"))
    else:
        set_current_database(os.environ.get("FABRIC_DATABASE", "contract-warehouse"))
        set_current_catalog_path(os.environ.get("CATALOG_DB_PATH", "./catalog.db"))

    decline = check_gate(message, agent_type)
    if decline:
        yield f"data: {json.dumps({'text': decline})}\n\n"
        yield "data: [DONE]\n\n"
        return

    username = sessions.get(session_id, {}).get("username", "unknown")
    mode_suffix = "reasoning" if is_harness else "fast"
    agent_key = agent_key or sessions.get(session_id, {}).get("agent_key") or f"{agent_type}-{mode_suffix}"

    # Persist user message to Cosmos DB before streaming the response, storing all strict tracking info
    await cosmos_db.save_message(
        session_id=session_id,
        role="user",
        content=message,
        user_id=username,
        agent_key=agent_key,
        agent_type=agent_type
    )

    # Update the session title in Cosmos DB from the user's message text.
    # This ensures the sidebar shows a meaningful title on next login instead of "New Chat".
    if username and username != "unknown":
        title = message[:30] + ("..." if len(message) > 30 else "")
        try:
            await cosmos_db.update_session_title(session_id, username, title)
        except Exception as e:
            print(f"Could not update session title: {e}")

    full_text = ""
    tool_calls_seen: list[str] = []

    try:
        stream = await agent.run(message, session=session_obj, stream=True)
        async for update in stream:
            if hasattr(update, "contents") and update.contents:
                for content in update.contents:
                    if content.type in ["function_call", "mcp_server_tool_call"]:
                        name = getattr(content, "name", None) or getattr(content, "tool_name", None)
                        if name:
                            # Prevent appending the same tool name multiple times during a stream
                            if not tool_calls_seen or tool_calls_seen[-1] != name:
                                tool_calls_seen.append(name)
                                if is_harness:
                                    yield f"data: {json.dumps({'text': f'<reasoning><tool_call name=\"{name}\" /></reasoning>', 'tool_call': name})}\n\n"
                                else:
                                    yield f"data: {json.dumps({'tool_call': name})}\n\n"

                    if is_harness and content.type in [
                        "function_call", "function_result",
                        "mcp_server_tool_call", "mcp_server_tool_result",
                    ]:
                        try:
                            todo_store = TodoSessionStore()
                            items = await todo_store.load_items(session_obj, source_id="todo")
                            if items:
                                todos = [
                                    {
                                        "id": item.id,
                                        "title": item.title,
                                        "description": item.description,
                                        "completed": item.completed,
                                        "reason": item.reason,
                                    }
                                    for item in items
                                ]
                                yield f"data: {json.dumps({'todos': todos})}\n\n"
                        except Exception:
                            pass

            if hasattr(update, "text") and update.text:
                full_text += update.text
                yield f"data: {json.dumps({'text': update.text})}\n\n"

        if is_harness:
            try:
                todo_store = TodoSessionStore()
                items = await todo_store.load_items(session_obj, source_id="todo")
                if items:
                    todos = [
                        {
                            "id": item.id,
                            "title": item.title,
                            "description": item.description,
                            "completed": item.completed,
                            "reason": item.reason,
                        }
                        for item in items
                    ]
                    yield f"data: {json.dumps({'todos': todos})}\n\n"
            except Exception:
                pass

    except Exception as inner_e:
        print(f"Error during streaming: {inner_e}")
        yield f"data: {json.dumps({'error': 'An error occurred while streaming the response.'})}\n\n"

    # Persist the completed assistant response to Cosmos DB
    if full_text:
        await cosmos_db.save_message(
            session_id=session_id,
            role="assistant",
            content=full_text,
            user_id=username,
            agent_key=agent_key,
            agent_type=agent_type,
            tool_calls=tool_calls_seen if tool_calls_seen else None,
            mode="reasoning" if is_harness else "fast"
        )

    yield "data: [DONE]\n\n"


def _chat_response(agent, obj_key: str, is_harness: bool, req: ChatRequest):
    session_data = _get_session_data(req.session_id)

    if not agent:
        async def _no_agent():
            yield f"data: {json.dumps({'error': 'Agent not initialized.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_agent(), media_type="text/event-stream")

    session_obj = _get_session_obj(session_data, agent, obj_key)
    return StreamingResponse(
        _stream_chat(agent, session_obj, req.session_id, req.message, is_harness, req.agent_type, req.agent_key),
        media_type="text/event-stream",
    )


@app.post("/chat")
async def chat(req: ChatRequest):
    """Reasoning mode — hit when the frontend's 'Reasoning' toggle is ON."""
    if req.agent_type == "aviation":
        return _chat_response(aviation_reasoning_agent, "obj_aviation_reasoning", True, req)
    return _chat_response(contracts_reasoning_agent, "obj_contracts_reasoning", True, req)


@app.post("/chat/fast")
async def chat_fast(req: ChatRequest):
    """Fast mode — hit when the frontend's 'Reasoning' toggle is OFF."""
    if req.agent_type == "aviation":
        return _chat_response(aviation_fast_agent, "obj_aviation_fast", False, req)
    return _chat_response(contracts_fast_agent, "obj_contracts_fast", False, req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
