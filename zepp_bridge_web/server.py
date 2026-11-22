import os
import json
import time
import secrets
import hashlib
import datetime
from typing import Optional, Dict, Any, List
import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, get_categories_overview, get_category_sample, get_category_records
from fetcher import ZeppDataSyncEngine
from auto_sync import start_auto_sync, trigger_sync

# Constants & Configuration
RELAY_BASE = "https://zeppbridge.com"
RELAY_FALLBACK_BASE = "https://zeppbridge.pages.dev"
ZEPP_API_BASE = "https://api-open.zepp.com"
SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")

# Initialize database schema
init_db()

app = FastAPI(title="Zepp MCP Data Bridge & Category Index")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Start periodic 15-minute auto-sync and launch immediate sync if session exists."""
    start_auto_sync(interval_seconds=900, startup_sync=True, startup_days=30, periodic_days=7)

# In-memory store for pending authorizations
pending_auths: Dict[str, Dict[str, Any]] = {}

def get_session() -> Optional[Dict[str, Any]]:
    """Load saved session tokens if present."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading session file: {e}")
    return None

def save_session(data: Dict[str, Any]):
    """Persist session tokens to local disk."""
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def clear_session():
    """Remove persisted session."""
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

def post_relay(path: str, body: Dict[str, Any]) -> requests.Response:
    """Send POST to the relay with automatic fallback."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    primary_url = f"{RELAY_BASE}{path}"
    try:
        resp = requests.post(primary_url, json=body, headers=headers, timeout=12)
        return resp
    except Exception as primary_err:
        print(f"Primary relay failed ({primary_err}), trying fallback...")
        fallback_url = f"{RELAY_FALLBACK_BASE}{path}"
        return requests.post(fallback_url, json=body, headers=headers, timeout=12)

def refresh_official_token(refresh_token: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Refresh the OAuth token through the relay."""
    try:
        resp = post_relay("/api/zepp/oauth/refresh", {
            "access_token": access_token,
            "refresh_token": refresh_token
        })
        if resp.status_code == 200:
            fresh = resp.json()
            session = get_session() or {}
            session["access_token"] = fresh["access_token"]
            if fresh.get("refresh_token"):
                session["refresh_token"] = fresh["refresh_token"]
            session["expires_at"] = int(time.time()) + fresh.get("expires_in", 7200)
            save_session(session)
            return session
    except Exception as e:
        print(f"Token refresh failed: {e}")
    return None

def get_valid_access_token() -> str:
    """Return a valid access token, auto-refreshing if expired."""
    session = get_session()
    if not session or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="No active Zepp session found. Please log in first.")
    
    expires_at = session.get("expires_at", 0)
    if expires_at and time.time() > (expires_at - 300) and session.get("refresh_token"):
        fresh = refresh_official_token(session["refresh_token"], session["access_token"])
        if fresh:
            return fresh["access_token"]
    
    return session["access_token"]

# --- API Endpoints ---

@app.get("/api/auth/status")
def auth_status():
    """Return whether user is logged in, profile details, and session metadata."""
    session = get_session()
    if not session or not session.get("access_token"):
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "user_id": session.get("user_id"),
        "nickname": session.get("nickname"),
        "connected_at": session.get("connected_at"),
        "expires_at": session.get("expires_at"),
    }

@app.post("/api/auth/start")
def auth_start():
    """Start OAuth flow."""
    state = secrets.token_urlsafe(32)
    claim_secret = secrets.token_urlsafe(32)
    claim_hash = hashlib.sha256(claim_secret.encode("utf-8")).hexdigest()
    
    pending_auths[state] = {
        "claim_secret": claim_secret,
        "created_at": time.time(),
        "status": "pending"
    }
    
    auth_url = f"{RELAY_BASE}/api/zepp/oauth/start?state={state}&claim={claim_hash}"
    return {
        "state": state,
        "auth_url": auth_url
    }

@app.get("/api/auth/poll")
def auth_poll(state: str = Query(...)):
    """Poll relay to claim tokens once user finishes browser authorization."""
    pending = pending_auths.get(state)
    if not pending:
        session = get_session()
        if session and session.get("access_token"):
            return {"status": "ready", "user_id": session.get("user_id")}
        raise HTTPException(status_code=404, detail="Auth state not recognized or expired.")
    
    claim_secret = pending["claim_secret"]
    
    try:
        resp = post_relay("/api/zepp/oauth/claim", {
            "state": state,
            "claim_secret": claim_secret
        })
    except Exception as e:
        return {"status": "pending", "message": f"Contacting relay... ({e})"}
    
    if resp.status_code == 202:
        return {"status": "pending", "message": "Waiting for authorization in browser..."}
    
    if resp.status_code == 404:
        pending_auths.pop(state, None)
        return {"status": "expired", "message": "Authorization request expired or already claimed."}
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "ready" and data.get("access_token"):
            now = int(time.time())
            user_id = data.get("user_id", "")
            
            nickname = None
            try:
                prof_resp = requests.get(
                    f"{ZEPP_API_BASE}/users/-/profile",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                    timeout=8
                )
                if prof_resp.status_code == 200:
                    prof_data = prof_resp.json()
                    user_id = str(prof_data.get("userId") or user_id)
                    nickname = prof_data.get("nickName")
            except Exception as pe:
                print(f"Profile lookup error: {pe}")
                
            session_data = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "user_id": user_id,
                "nickname": nickname,
                "connected_at": now,
                "expires_at": now + data.get("expires_in", 7200)
            }
            save_session(session_data)
            pending_auths.pop(state, None)
            # Trigger immediate background sync for newly connected account
            import threading
            threading.Thread(target=trigger_sync, kwargs={"days": 90, "force": True, "reason": "post-login"}, daemon=True).start()
            return {"status": "ready", "user_id": user_id, "nickname": nickname}
        else:
            return {"status": data.get("status", "failed"), "message": data.get("error")}
            
    return {"status": "failed", "message": f"Relay returned HTTP {resp.status_code}"}

@app.post("/api/auth/disconnect")
def auth_disconnect():
    """Disconnect session and clear saved tokens."""
    session = get_session()
    if session and session.get("access_token"):
        try:
            requests.post(
                f"{ZEPP_API_BASE}/users/-/thirdparty/unauthorize",
                headers={"Authorization": f"Bearer {session['access_token']}"},
                json={},
                timeout=5
            )
        except Exception:
            pass
    clear_session()
    return {"success": True, "message": "Logged out successfully."}

@app.post("/api/sync")
def sync_data(days: int = Query(default=90, ge=1, le=365)):
    """
    Triggers full multi-category synchronization from Zepp into local SQLite.
    Returns the count of records synced per category.
    """
    token = get_valid_access_token()
    engine = ZeppDataSyncEngine(token)
    results = engine.sync_all(days=days)
    return {
        "status": "success",
        "synced_counts": results,
        "probed_days": days
    }

@app.get("/api/categories")
def get_categories():
    """
    Returns the organized Category Catalog for the MCP data layer:
    - id, name, icon, description, mcp_intent
    - total_entries count in SQLite
    - date_range (from, to)
    - schema fields and descriptions
    - readiness status
    """
    return get_categories_overview()

@app.get("/api/categories/{category_id}/sample")
def get_sample(category_id: str):
    """Returns the most recent single record in the specified category."""
    sample = get_category_sample(category_id)
    if not sample:
        raise HTTPException(status_code=404, detail="No records found in this category yet.")
    return sample

@app.get("/api/categories/{category_id}/records")
def get_records(category_id: str, limit: int = Query(default=20, ge=1, le=100)):
    """Returns up to `limit` most recent records in the specified category."""
    records = get_category_records(category_id, limit=limit)
    return records

# Serve UI
@app.get("/", response_class=HTMLResponse)
def index_page():
    html_file = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(html_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
