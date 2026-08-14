from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import time
import uuid
import sys
import os

# Ensure the current directory is in sys.path so we can import from agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent import build_reasoning_agent, build_fast_agent
from agent_framework._harness._todo import TodoSessionStore

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize both agent variants globally.
#   - reasoning_agent: original harness agent (todo tracking + narrated
#     <reasoning> before every tool call). Hit by POST /chat.
#   - fast_agent: plain tool-calling agent, no todo/harness scaffolding, no
#     narrated reasoning. Hit by POST /chat/fast.
# Both run the exact same tool pipeline underneath, so accuracy is the same;
# only latency and how much process is shown to the user differs.
try:
    reasoning_agent = build_reasoning_agent()
except Exception as e:
    print(f"Warning: Could not build reasoning agent on startup: {e}")
    reasoning_agent = None

try:
    fast_agent = build_fast_agent()
except Exception as e:
    print(f"Warning: Could not build fast agent on startup: {e}")
    fast_agent = None

sessions = {}
SESSION_TIMEOUT = 30 * 60  # 30 minutes


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str
    session_id: str


@app.post("/login")
async def login(req: LoginRequest):
    if req.username and req.password:
        session_id = str(uuid.uuid4())
        # Each conversation gets its own session object per agent variant,
        # created lazily on first use in _get_session_obj below — a fresh
        # login shouldn't pay the cost of spinning up both if the user only
        # ever uses one toggle position.
        sessions[session_id] = {
            "obj_reasoning": None,
            "obj_fast": None,
            "last_active": time.time(),
        }
        return {"session_id": session_id, "expires_in": SESSION_TIMEOUT}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/logout")
async def logout(req: Request):
    auth_header = req.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_id = auth_header.split(" ")[1]
        if session_id in sessions:
            del sessions[session_id]
            return {"status": "logged_out"}
    return {"status": "ok"}


def _get_session_data(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    session_data = sessions[session_id]
    if time.time() - session_data["last_active"] > SESSION_TIMEOUT:
        del sessions[session_id]
        raise HTTPException(status_code=401, detail="Session expired")
    session_data["last_active"] = time.time()
    return session_data


def _get_session_obj(session_data: dict, agent, obj_key: str):
    """Lazily create (and cache) the per-agent session object. Note: the
    reasoning and fast agents are two different Agent instances, so they
    each need their own session/conversation-thread object — switching the
    toggle mid-conversation starts that mode's own thread rather than
    sharing history with the other mode."""
    if session_data[obj_key] is None and agent is not None:
        session_data[obj_key] = agent.create_session()
    return session_data[obj_key]


async def _stream_chat(agent, session_obj, message: str, is_harness: bool):
    """Shared SSE generator for both the reasoning and fast agents.

    is_harness controls two harness-only behaviors that the plain fast
    agent doesn't have: (1) todo-list syncing, and (2) emitting the
    <reasoning><tool_call .../></reasoning> text markers that the frontend's
    "Thought process" panel parses. The fast agent still reports which
    tools it called (via the bare 'tool_call' field) so the frontend can
    show a lightweight "verified with" chip instead — it just doesn't wrap
    that into visible reasoning text.
    """
    try:
        stream = await agent.run(message, session=session_obj, stream=True)
        async for update in stream:
            if hasattr(update, "contents") and update.contents:
                for content in update.contents:
                    if content.type in ["function_call", "mcp_server_tool_call"]:
                        name = getattr(content, "name", None) or getattr(content, "tool_name", None)
                        if name:
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
        _stream_chat(agent, session_obj, req.message, is_harness),
        media_type="text/event-stream",
    )


@app.post("/chat")
async def chat(req: ChatRequest):
    """Reasoning mode — hit when the frontend's 'Reasoning' toggle is ON."""
    return _chat_response(reasoning_agent, "obj_reasoning", True, req)


@app.post("/chat/fast")
async def chat_fast(req: ChatRequest):
    """Fast mode — hit when the frontend's 'Reasoning' toggle is OFF."""
    return _chat_response(fast_agent, "obj_fast", False, req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
