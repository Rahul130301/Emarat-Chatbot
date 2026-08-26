"""
Azure AD SSO Authentication Router
Implements OAuth2 Authorization Code Flow for Microsoft Azure AD login.

Endpoints:
    GET  /api/v1/auth/azure-ad/login     → Redirect to Microsoft login page
    GET  /api/v1/auth/azure-ad/callback  → Handle Microsoft callback, set session cookie
    GET  /api/v1/auth/me                 → Return current user info from cookie
    POST /api/v1/auth/logout             → Clear session cookie
"""

import os
import time
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import cosmos_db
from session_store import sessions, SESSION_TIMEOUT, make_session_entry

# ── Azure AD config ──────────────────────────────────────────────────────────
TENANT_ID     = os.environ.get("ALDAR_AZURE_TENANT_ID", "")
CLIENT_ID     = os.environ.get("ALDAR_AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ALDAR_AZURE_CLIENT_SECRET", "")
REDIRECT_URI  = os.environ.get("SSO_REDIRECT_URI",  "http://localhost:8000/api/v1/auth/azure-ad/callback")
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "http://localhost:5173")
SECRET_KEY    = os.environ.get("SESSION_SECRET_KEY", "please-change-this-to-a-random-secret-32+chars")

AUTHORITY  = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES     = ["openid", "profile", "email", "User.Read"]
COOKIE_NAME = "emarat_session"

router = APIRouter(prefix="/api/v1/auth", tags=["SSO Auth"])
signer = URLSafeTimedSerializer(SECRET_KEY)


# ── 1. Redirect to Microsoft login ──────────────────────────────────────────
@router.get("/azure-ad/login", summary="Azure AD Login")
async def azure_ad_login():
    """
    Redirects the browser to the Microsoft Azure AD login page.
    A random `state` value is stored in a short-lived cookie for CSRF protection.
    """
    if not TENANT_ID or not CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="SSO is not configured. Set ALDAR_AZURE_TENANT_ID and ALDAR_AZURE_CLIENT_ID in .env"
        )

    state = str(uuid.uuid4())
    params = {
        "client_id":     CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  REDIRECT_URI,
        "response_mode": "query",
        "scope":         " ".join(SCOPES),
        "state":         state,
    }
    auth_url = f"{AUTHORITY}/oauth2/v2.0/authorize?{urlencode(params)}"

    resp = RedirectResponse(url=auth_url, status_code=302)
    # Store signed state in short-lived cookie (10 min) for CSRF verification
    resp.set_cookie(
        key="oauth_state",
        value=signer.dumps(state),
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=False,   # Set True in production (HTTPS)
    )
    return resp


# ── 2. Microsoft callback ────────────────────────────────────────────────────
@router.get("/azure-ad/callback", summary="Azure AD Callback")
async def azure_ad_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """
    Microsoft redirects here after the user logs in.
    Exchanges the auth code for tokens, reads user profile from MS Graph,
    creates/resumes a Cosmos DB session, and sets a signed HTTP-only session cookie.
    Then redirects back to the frontend with ?sso=ok.
    """
    # Handle Microsoft-reported error (e.g. user cancelled login)
    if error:
        return RedirectResponse(
            url=f"{FRONTEND_URL}?sso_error={error}",
            status_code=302
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state parameter.")

    # ── CSRF: validate the state cookie ─────────────────────────────────────
    signed_state = request.cookies.get("oauth_state")
    if not signed_state:
        raise HTTPException(status_code=400, detail="Missing OAuth state cookie. Please try logging in again.")

    try:
        stored_state = signer.loads(signed_state, max_age=600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Login session expired. Please try again.")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid state parameter. Possible CSRF attempt.")

    if stored_state != state:
        raise HTTPException(status_code=400, detail="State mismatch. Possible CSRF attempt.")

    # ── Exchange auth code for access token ──────────────────────────────────
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            f"{AUTHORITY}/oauth2/v2.0/token",
            data={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_response.status_code != 200:
        print(f"Token exchange failed: {token_response.text}")
        raise HTTPException(status_code=401, detail="Failed to exchange authorization code for tokens.")

    tokens = token_response.json()
    access_token = tokens.get("access_token")

    if not access_token:
        raise HTTPException(status_code=401, detail="No access token received from Microsoft.")

    # ── Fetch user profile from Microsoft Graph ──────────────────────────────
    async with httpx.AsyncClient() as client:
        graph_response = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if graph_response.status_code != 200:
        print(f"Graph API failed: {graph_response.text}")
        raise HTTPException(status_code=401, detail="Failed to retrieve user profile from Microsoft.")

    user_profile = graph_response.json()
    # Use userPrincipalName (email/UPN) as the stable user ID for Cosmos DB
    username     = user_profile.get("userPrincipalName") or user_profile.get("mail") or user_profile.get("id")
    display_name = user_profile.get("displayName") or username
    email        = user_profile.get("mail") or user_profile.get("userPrincipalName", "")

    print(f"SSO login: {display_name} ({username})")

    # ── Create or resume Cosmos DB session ───────────────────────────────────
    # Fetch any existing session (no agent_key filter — just to check if first-time user)
    existing_sessions = await cosmos_db.get_user_sessions(user_id=username)

    if existing_sessions:
        # Resume the most recent session (from any agent)
        session_id = existing_sessions[0]["id"]
    else:
        # First-time user — create a fresh session defaulting to contracts-fast
        session_id = await cosmos_db.create_session(
            user_id=username,
            title="New Chat",
            agent_key="contracts-fast"
        )

    # Register in in-memory store (creates LLM agent objects lazily on first use)
    if session_id not in sessions:
        sessions[session_id] = make_session_entry(username, display_name, email)
    else:
        sessions[session_id]["last_active"] = time.time()

    # ── Issue signed session cookie ───────────────────────────────────────────
    session_payload = {
        "session_id":   session_id,
        "username":     username,
        "display_name": display_name,
        "email":        email,
    }
    signed_cookie = signer.dumps(session_payload)

    resp = RedirectResponse(url=f"{FRONTEND_URL}?sso=ok", status_code=302)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=signed_cookie,
        httponly=True,       # Not accessible from JavaScript (security)
        max_age=SESSION_TIMEOUT,
        samesite="lax",
        secure=False,        # Set True in production (HTTPS only)
    )
    resp.delete_cookie("oauth_state")  # Clean up the CSRF state cookie
    return resp


# ── 3. Get current user info ─────────────────────────────────────────────────
@router.get("/me", summary="Get Current User Info")
async def get_current_user(request: Request):
    """
    Reads the signed session cookie and returns the current user's info.
    Returns 401 if the user is not authenticated or the session has expired.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    try:
        payload = signer.loads(token, max_age=SESSION_TIMEOUT)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session. Please log in again.")

    session_id   = payload.get("session_id")
    username     = payload.get("username")
    display_name = payload.get("display_name")
    email        = payload.get("email")

    # Re-register session in memory if the server was restarted
    if session_id and session_id not in sessions:
        sessions[session_id] = make_session_entry(username, display_name, email)

    return {
        "session_id":   session_id,
        "username":     username,
        "display_name": display_name,
        "email":        email,
    }


# ── 4. Logout ────────────────────────────────────────────────────────────────
@router.post("/logout", summary="Logout (clear session cookie)")
async def sso_logout(request: Request):
    """
    Clears the session cookie and removes the session from the in-memory store.
    """
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = signer.loads(token, max_age=SESSION_TIMEOUT)
            sid = payload.get("session_id")
            if sid and sid in sessions:
                del sessions[sid]
        except Exception:
            pass  # Cookie was invalid; still clear it

    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(COOKIE_NAME)
    return resp
