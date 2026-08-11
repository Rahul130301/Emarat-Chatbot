from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import uuid
import sys
import os

# Ensure the current directory is in sys.path so we can import from agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent import build_agent

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent globally
try:
    agent = build_agent()
except Exception as e:
    print(f"Warning: Could not build agent on startup: {e}")
    agent = None

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
        session_obj = agent.create_session() if agent else None
        sessions[session_id] = {
            "obj": session_obj,
            "last_active": time.time()
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

@app.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    
    session_data = sessions[session_id]
    
    if time.time() - session_data["last_active"] > SESSION_TIMEOUT:
        del sessions[session_id]
        raise HTTPException(status_code=401, detail="Session expired")
    
    session_data["last_active"] = time.time()
    
    if not agent:
        return {"response": "Agent not initialized."}
        
    try:
        result = await agent.run(req.message, session=session_data["obj"])
        print(f"\n=== AGENT RESPONSE ===\n{result.text}\n=== END RESPONSE ===\n")
        return {"response": result.text}
    except Exception as e:
        print(f"Error during agent run: {e}")
        return {"response": "An error occurred while processing the request."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
