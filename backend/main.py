"""FastAPI backend for the virtual classroom of agents."""

import json
import os
import secrets

import anthropic
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import auth
import billing
import db
import orchestrator
import slack_bot
from agents import POOL, TEACHER

WEB_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "dist")

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
    plan: dict | None = None  # an approved lesson plan from POST /api/lesson-plan; omit for a "review" session


class LessonPlanRequest(BaseModel):
    topic: str
    pool_keys: list[str] | None = None


ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB decoded


class ImageAttachment(BaseModel):
    media_type: str
    data: str  # base64, no "data:...;base64," prefix


class MessageRequest(BaseModel):
    session_id: str
    text: str
    image: ImageAttachment | None = None


def _validate_image(image: ImageAttachment | None):
    if not image:
        return
    if image.media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="סוג קובץ לא נתמך. אפשר PNG, JPEG, WEBP או GIF.")
    # base64 expands size by ~4/3; estimate the decoded size without actually decoding.
    approx_decoded_bytes = len(image.data) * 3 / 4
    if approx_decoded_bytes > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="הקובץ גדול מדי (מקסימום 5MB).")


@app.get("/api/agents")
def list_agents():
    return {
        "teacher": {"key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color},
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in POOL],
    }


@app.post("/api/lesson-plan")
def create_lesson_plan(req: LessonPlanRequest, x_anthropic_key: str | None = Header(default=None)):
    """Preview-only: generates a lesson plan for the user to approve or
    regenerate before any session/DB row exists. Creating the actual session
    (POST /api/session) with the approved plan attached is a separate step."""
    try:
        pool = orchestrator.resolve_pool(req.topic, req.pool_keys)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        plan = orchestrator.generate_lesson_plan(req.topic, pool, api_key=x_anthropic_key)
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
    except orchestrator.LessonPlanGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"plan": plan, "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in pool]}


@app.post("/api/session")
def create_session(req: CreateSessionRequest, request: Request):
    user = request.session.get("user")
    user_email = user["email"] if user else None
    billing.check_lesson_quota(user_email)
    try:
        session = orchestrator.create_session(
            req.topic, pool_keys=req.pool_keys, user_email=user_email, plan=req.plan
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "session_id": session.id,
        "topic": session.topic,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in session.pool],
        "plan": session.plan,
        "awaiting_user": session.awaiting_user,
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
        "plan": session.plan,
        "activity_index": session.activity_index,
        "awaiting_user": session.awaiting_user,
    }


@app.get("/api/lessons")
def list_lessons(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    return {"lessons": db.list_lessons_for_user(user["email"])}


def _image_dict(image: ImageAttachment | None) -> dict | None:
    return {"media_type": image.media_type, "data": image.data} if image else None


@app.post("/api/message")
def send_message(req: MessageRequest, x_anthropic_key: str | None = Header(default=None)):
    _validate_image(req.image)
    try:
        session = orchestrator.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        replies = orchestrator.handle_user_message(
            session, req.text, api_key=x_anthropic_key, image=_image_dict(req.image)
        )
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


@app.post("/api/message/stream")
def send_message_stream(req: MessageRequest, x_anthropic_key: str | None = Header(default=None)):
    """Server-Sent Events version of /api/message: each agent's reply is
    delivered as it's generated (word-by-word for the verified teacher,
    live model tokens for everyone else) instead of all at once at the end.

    Errors (missing/invalid key, etc.) are delivered as an SSE event with
    type "error" rather than an HTTP error status — by the time this starts
    streaming, the 200 response has already begun, so the status code can't
    change anymore. See orchestrator.handle_user_message_stream for why.

    The image attachment is validated eagerly (type/size), before the stream
    starts, since that check doesn't depend on the model and can still
    return a normal HTTP error status."""
    _validate_image(req.image)
    try:
        session = orchestrator.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    def event_source():
        stream = orchestrator.handle_user_message_stream(
            session, req.text, api_key=x_anthropic_key, image=_image_dict(req.image)
        )
        for event in stream:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/session/{session_id}/continue/stream")
def continue_lesson_stream(session_id: str, x_anthropic_key: str | None = Header(default=None)):
    """SSE, same event shape as /api/message/stream, but with no new user
    text — produces exactly one autonomous 'beat' of a plan-driven lesson.
    See orchestrator.advance_lesson_stream for the state machine."""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    def event_source():
        for event in orchestrator.advance_lesson_stream(session, api_key=x_anthropic_key):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/session/{session_id}/quiz")
def create_quiz(session_id: str, x_anthropic_key: str | None = Header(default=None)):
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    if session.round_count < 1:
        raise HTTPException(status_code=400, detail="אין עדיין מספיק שיחה בשיעור כדי לבנות בוחן.")

    try:
        questions = orchestrator.generate_quiz(session, api_key=x_anthropic_key)
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
    except orchestrator.QuizGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"questions": questions}


app.include_router(slack_bot.router)
app.include_router(auth.router)
app.include_router(billing.router)

# Serve the built React app (web/dist). Vite's hashed JS/CSS live under
# /assets; everything else (including client-side routes like /pricing or
# /app that have no matching file on disk) falls back to index.html so
# React Router can take over — this must stay the LAST route registered,
# since FastAPI matches routes in registration order and every API route
# above needs to win first.
app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="web-assets")


@app.get("/favicon.svg")
def favicon():
    return FileResponse(os.path.join(WEB_DIST, "favicon.svg"))


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    return FileResponse(os.path.join(WEB_DIST, "index.html"))
