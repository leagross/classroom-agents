"""FastAPI backend for the virtual classroom of agents."""

import json
import os
import secrets

import time

import anthropic
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import auth
import billing
import db
import flashcards
import lesson_plan
import orchestrator
import quiz
import session_state
import slack_bot
import syllabus
from agent_calls import TEACHER_REPLAY_DELAY, MissingApiKeyError, word_chunks
from agents import POOL, TEACHER
from services.session_repository import lesson_from_row

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
    syllabus_id: str | None = None  # set together when starting a lesson picked from a syllabus
    syllabus_lesson_index: int | None = None


class LessonPlanRequest(BaseModel):
    topic: str
    pool_keys: list[str] | None = None


class SyllabusRequest(BaseModel):
    topic: str


class CreateSyllabusRequest(BaseModel):
    topic: str
    lessons: list[dict]


ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB decoded

API_KEY_MISSING_DETAIL = "לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑)."
API_KEY_INVALID_DETAIL = "מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב."


@app.exception_handler(MissingApiKeyError)
def _missing_api_key_handler(request: Request, exc: MissingApiKeyError):
    """One place that turns a missing/invalid key into an HTTP error, instead
    of the same try/except pair repeated in six route bodies."""
    return JSONResponse(status_code=401, content={"detail": API_KEY_MISSING_DETAIL})


@app.exception_handler(anthropic.AuthenticationError)
def _invalid_api_key_handler(request: Request, exc: anthropic.AuthenticationError):
    return JSONResponse(status_code=401, content={"detail": API_KEY_INVALID_DETAIL})


def _sse(events):
    """Adapter from the orchestrator's event generator to the SSE wire
    format. Pacing lives here, not in the pipeline: a 'start' event marked
    replay=True is already-generated text (the verified teacher), so it's
    delivered word by word to read like live typing. Non-streaming callers
    of the same pipeline pay none of this."""
    paced = False
    for event in events:
        if event.get("type") == "start":
            paced = bool(event.get("replay"))
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        elif event.get("type") == "token" and paced:
            for chunk in word_chunks(event["text"]):
                yield f"data: {json.dumps({'type': 'token', 'text': chunk}, ensure_ascii=False)}\n\n"
                time.sleep(TEACHER_REPLAY_DELAY)
        else:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


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
        pool = session_state.resolve_pool(req.topic, req.pool_keys)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        plan = lesson_plan.generate_lesson_plan(req.topic, pool, api_key=x_anthropic_key)
    except lesson_plan.LessonPlanGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"plan": plan, "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in pool]}


@app.post("/api/session")
def create_session(req: CreateSessionRequest, request: Request):
    user = request.session.get("user")
    user_email = user["email"] if user else None
    billing.check_lesson_quota(user_email)
    try:
        session = session_state.create_session(
            req.topic, pool_keys=req.pool_keys, user_email=user_email, plan=req.plan,
            syllabus_id=req.syllabus_id, syllabus_lesson_index=req.syllabus_lesson_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.syllabus_id is not None and req.syllabus_lesson_index is not None:
        try:
            syllabus.mark_lesson_started(req.syllabus_id, req.syllabus_lesson_index, session.id)
        except KeyError:
            pass  # the syllabus itself is gone (e.g. DB-less restart) — the lesson still works standalone
    return {
        "session_id": session.id,
        "topic": session.topic,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in session.pool],
        "plan": session.lesson.plan,
        "awaiting_user": session.lesson.autoplay_paused,
    }


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    """Fetch a lesson's full state (topic, pool, history) so the frontend can
    resume it — either a session still cached in this process, or one
    rehydrated from the DB (e.g. after a restart, or opened on another device
    for a logged-in user)."""
    try:
        session = session_state.get_session(session_id)
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
        "plan": session.lesson.plan,
        "activity_index": session.lesson.activity_index,
        "awaiting_user": session.lesson.autoplay_paused,
        "teacher_mode": session.lesson.mode.value,
        "syllabus_id": session.syllabus_id,
    }


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    """Removes a lesson from history (sidebar/dashboard) — in-memory cache
    and the DB row (messages cascade-delete with it). Idempotent: deleting
    an id that's already gone, or was never persisted, is not an error."""
    session_state.delete_session(session_id)
    return {"ok": True}


@app.post("/api/syllabus")
def create_syllabus_preview(req: SyllabusRequest, x_anthropic_key: str | None = Header(default=None)):
    """Preview-only, same spirit as POST /api/lesson-plan: breaks a broad
    topic into a lesson outline (title + summary each) for the user to
    approve or regenerate, before any syllabus/DB row exists. Each lesson's
    own full plan is generated separately, lazily, only once started."""
    try:
        lessons = syllabus.generate_syllabus(req.topic, api_key=x_anthropic_key)
    except syllabus.SyllabusGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"topic": req.topic, "lessons": lessons}


@app.post("/api/syllabus/create")
def create_syllabus(req: CreateSyllabusRequest, request: Request):
    user = request.session.get("user")
    user_email = user["email"] if user else None
    syl = syllabus.create_syllabus(req.topic, req.lessons, user_email=user_email)
    return syl


@app.get("/api/syllabus/{syllabus_id}")
def get_syllabus(syllabus_id: str):
    try:
        return syllabus.get_syllabus(syllabus_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="syllabus not found")


@app.get("/api/syllabi")
def list_syllabi(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    return {"syllabi": db.list_syllabi_for_user(user["email"])}


@app.post("/api/syllabus/{syllabus_id}/lesson/{lesson_index}/plan")
def create_syllabus_lesson_plan(
    syllabus_id: str, lesson_index: int, x_anthropic_key: str | None = Header(default=None)
):
    """Generates (preview-only, like POST /api/lesson-plan) the full 5-stage
    plan for one specific lesson in a syllabus — only called when the
    student actually starts that lesson, not when the syllabus itself was
    created."""
    try:
        syl = syllabus.get_syllabus(syllabus_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="syllabus not found")
    if not (0 <= lesson_index < len(syl["lessons"])):
        raise HTTPException(status_code=404, detail="lesson index out of range")

    lesson = syl["lessons"][lesson_index]
    combined_topic = f"{syl['topic']} — {lesson['title']}"
    try:
        pool = session_state.resolve_pool(combined_topic, None)
        plan = lesson_plan.generate_lesson_plan(combined_topic, pool, api_key=x_anthropic_key)
    except lesson_plan.LessonPlanGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "topic": combined_topic,
        "plan": plan,
        "pool": [{"key": a.key, "name": a.display_name, "color": a.color} for a in pool],
    }


@app.get("/api/lessons")
def list_lessons(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    return {"lessons": db.list_lessons_for_user(user["email"])}


def _lesson_status(row: dict) -> str:
    """A "review" lesson has no defined end, so it's never in_progress/
    completed in the dashboard's sense — just its own thing.

    This used to be a fourth independent re-derivation of "where is this
    lesson", with its own boolean comparison. It now rebuilds the actual
    Lesson state machine from the row and asks it, so the dashboard can't
    disagree with the classroom about whether a lesson is finished."""
    if not row.get("plan"):
        return "review"
    return "completed" if lesson_from_row(row).is_complete() else "in_progress"


@app.get("/api/dashboard")
def get_dashboard(request: Request):
    """Aggregate progress view for a signed-in user: how many lessons/
    syllabi they've completed or are mid-way through, and which topics
    they've covered — built from the same rows /api/lessons and /api/syllabi
    already expose, just summarized."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    email = user["email"]

    lessons = db.list_lessons_for_user(email, limit=100)
    for lesson in lessons:
        lesson["status"] = _lesson_status(lesson)
        lesson.pop("plan", None)  # the full plan isn't needed by the dashboard view

    syllabi = db.list_syllabi_for_user(email, limit=50)
    syllabus_summaries = [
        {
            "id": s["id"],
            "topic": s["topic"],
            "total_lessons": len(s["lessons"]),
            "completed_lessons": sum(1 for l in s["lessons"] if l["status"] == "completed"),
        }
        for s in syllabi
    ]

    return {
        "total_lessons": len(lessons),
        "completed_lessons": sum(1 for l in lessons if l["status"] == "completed"),
        "in_progress_lessons": sum(1 for l in lessons if l["status"] == "in_progress"),
        "topics_covered": sorted({l["topic"] for l in lessons}),
        "syllabi": syllabus_summaries,
        "recent_lessons": lessons[:10],
    }


def _image_dict(image: ImageAttachment | None) -> dict | None:
    return {"media_type": image.media_type, "data": image.data} if image else None


@app.post("/api/message")
def send_message(req: MessageRequest, x_anthropic_key: str | None = Header(default=None)):
    _validate_image(req.image)
    try:
        session = session_state.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    # Same pipeline as the SSE route below, just drained to a list — so a
    # plan-driven lesson advances identically on both, which was the bug
    # this rewrite set out to remove.
    try:
        replies = orchestrator.handle_user_message(
            session, req.text, api_key=x_anthropic_key, image=_image_dict(req.image)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
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
    change anymore. See orchestrator._guarded for why.

    The image attachment is validated eagerly (type/size), before the stream
    starts, since that check doesn't depend on the model and can still
    return a normal HTTP error status."""
    _validate_image(req.image)
    try:
        session = session_state.get_session(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    events = orchestrator.user_message_events(
        session, req.text, api_key=x_anthropic_key, image=_image_dict(req.image)
    )
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/session/{session_id}/continue/stream")
def continue_lesson_stream(session_id: str, x_anthropic_key: str | None = Header(default=None)):
    """SSE, same event shape as /api/message/stream, but with no new user
    text — produces exactly one autonomous 'beat' of a plan-driven lesson.
    See orchestrator.autonomous_beat_events, which dispatches on the
    lesson's TeacherMode."""
    try:
        session = session_state.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    return StreamingResponse(
        _sse(orchestrator.autonomous_beat_events(session, api_key=x_anthropic_key)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/session/{session_id}/quiz")
def create_quiz(session_id: str, x_anthropic_key: str | None = Header(default=None)):
    try:
        session = session_state.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    if session.round_count < 1:
        raise HTTPException(status_code=400, detail="אין עדיין מספיק שיחה בשיעור כדי לבנות בוחן.")

    try:
        questions = quiz.generate_quiz(session, api_key=x_anthropic_key)
    except quiz.QuizGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"questions": questions}


@app.post("/api/session/{session_id}/flashcards")
def create_flashcards(session_id: str, x_anthropic_key: str | None = Header(default=None)):
    try:
        session = session_state.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    if session.round_count < 1:
        raise HTTPException(status_code=400, detail="אין עדיין מספיק שיחה בשיעור כדי לבנות כרטיסיות.")

    try:
        cards = flashcards.generate_flashcards(session, api_key=x_anthropic_key)
    except flashcards.FlashcardsGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"cards": cards}


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
