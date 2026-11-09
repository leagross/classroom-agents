"""FastAPI backend for the virtual classroom of agents."""

import os
import secrets

import anthropic
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import auth
import db
import orchestrator
import slack_bot
from agents import POOL, TEACHER

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

app = FastAPI(title="Classroom of Agents")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# SESSION_SECRET should be set explicitly in production (Render env var) so
# login sessions survive restarts/deploys; falling back to a random secret
# here only affects local dev, where losing login state on restart is fine.
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET") or secrets.token_hex(32))


class CreateSessionRequest(BaseModel):
    topic: str
    pool_keys: list[str] | None = None  # exactly 2 keys from POOL, or None for auto-selection


class MessageRequest(BaseModel):
    session_id: str
    text: str


@app.get("/api/agents")
def list_agents():
    return {
        "teacher": {"key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color},
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in POOL],
    }


@app.post("/api/session")
def create_session(req: CreateSessionRequest, request: Request):
    user = request.session.get("user")
    user_email = user["email"] if user else None
    try:
        session = orchestrator.create_session(req.topic, pool_keys=req.pool_keys, user_email=user_email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "session_id": session.id,
        "topic": session.topic,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in session.pool],
    }


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    """Fetch a lesson's full state (topic, pool, history) so the frontend can
    resume it — either a session still cached in this process, or one
    rehydrated from the DB (e.g. after a restart, or opened on another device
    for a logged-in user)."""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": session.id,
        "topic": session.topic,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in session.pool],
        "history": [
            {
                "agent": m.display_name,
                "key": m.agent_key,
                "color": m.color,
                "text": m.content,
                "is_user": m.agent_key == "user",
            }
            for m in session.history
        ],
    }


@app.get("/api/lessons")
def list_lessons(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    return {"lessons": db.list_lessons_for_user(user["email"])}


@app.post("/api/message")
def send_message(req: MessageRequest, x_anthropic_key: str | None = Header(default=None)):
    try:
        session = orchestrator.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        replies = orchestrator.handle_user_message(session, req.text, api_key=x_anthropic_key)
    except orchestrator.MissingApiKeyError:
        raise HTTPException(
            status_code=401,
            detail="לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑).",
        )
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב.",
        )
    return {
        "replies": [
            {"agent": m.display_name, "key": m.agent_key, "color": m.color, "text": m.content}
            for m in replies
        ]
    }


app.include_router(slack_bot.router)
app.include_router(auth.router)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
