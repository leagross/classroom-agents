"""FastAPI backend for the virtual classroom of agents."""

import os

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
def create_session(req: CreateSessionRequest):
    try:
        session = orchestrator.create_session(req.topic, pool_keys=req.pool_keys)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "session_id": session.id,
        "topic": session.topic,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in session.pool],
    }


@app.post("/api/message")
def send_message(req: MessageRequest, x_anthropic_key: str | None = Header(default=None)):
    try:
        session = orchestrator.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        replies = orchestrator.handle_user_message(session, req.text, api_key=x_anthropic_key)
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

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
