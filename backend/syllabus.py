"""A syllabus: a broad topic broken into several lessons up front, each
lesson's own full 5-stage plan (see lesson_plan.py) generated lazily, only
once the student actually starts that specific lesson — not all at once.

Mirrors session_state.py's pattern: an in-memory dict as the fast path,
with the DB (if configured) as the source of truth that survives restarts.
"""

import json
import os
import uuid

import db
from agent_calls import MODEL, get_client
from agents import SYLLABUS_SYSTEM_PROMPT
from json_utils import extract_json

SYLLABUS_MODEL = os.environ.get("CLASSROOM_SYLLABUS_MODEL", MODEL)
SYLLABUS_MAX_TOKENS = 1500
SYLLABUS_MAX_RETRIES = 2


class SyllabusGenerationError(Exception):
    pass


def generate_syllabus(topic: str, api_key: str | None = None) -> list:
    """Returns a list of {"title", "summary"} dicts — the lesson outline,
    before any individual lesson's full plan exists."""
    user_content = f"נושא רחב ללימוד: {topic}"
    last_error = None
    for _ in range(SYLLABUS_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=SYLLABUS_MODEL,
            max_tokens=SYLLABUS_MAX_TOKENS,
            system=SYLLABUS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            lessons = extract_json(raw)
            if not isinstance(lessons, list) or not lessons:
                raise ValueError("expected a non-empty JSON array")
            for lesson in lessons:
                if not (isinstance(lesson.get("title"), str) and lesson["title"]):
                    raise ValueError("lesson missing title")
                if not isinstance(lesson.get("summary"), str):
                    lesson["summary"] = ""
            return lessons
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError) as e:
            last_error = e
            print(f"[generate_syllabus] malformed syllabus JSON, retrying: {e}; raw={raw[:300]!r}")

    raise SyllabusGenerationError(f"לא הצלחתי לבנות סילבוס תקין: {last_error}")


SYLLABI: dict[str, dict] = {}


def create_syllabus(topic: str, lessons: list, user_email: str | None = None) -> dict:
    syllabus_id = str(uuid.uuid4())
    stored_lessons = [
        {
            "title": lesson["title"],
            "summary": lesson.get("summary", ""),
            "status": "not_started",  # not_started | in_progress | completed
            "session_id": None,
        }
        for lesson in lessons
    ]
    syllabus = {"id": syllabus_id, "topic": topic, "lessons": stored_lessons, "user_email": user_email}
    SYLLABI[syllabus_id] = syllabus
    db.insert_syllabus(syllabus_id, topic, stored_lessons, user_email)
    return syllabus


def get_syllabus(syllabus_id: str) -> dict:
    if syllabus_id in SYLLABI:
        return SYLLABI[syllabus_id]
    syllabus = db.load_syllabus(syllabus_id)
    if not syllabus:
        raise KeyError("syllabus not found")
    SYLLABI[syllabus_id] = syllabus
    return syllabus


def _save(syllabus: dict):
    db.update_syllabus_lessons(syllabus["id"], syllabus["lessons"])


def mark_lesson_started(syllabus_id: str, lesson_index: int, session_id: str):
    syllabus = get_syllabus(syllabus_id)
    lessons = syllabus["lessons"]
    if 0 <= lesson_index < len(lessons):
        lessons[lesson_index]["status"] = "in_progress"
        lessons[lesson_index]["session_id"] = session_id
        _save(syllabus)


def mark_lesson_completed(syllabus_id: str, lesson_index: int):
    syllabus = get_syllabus(syllabus_id)
    lessons = syllabus["lessons"]
    if 0 <= lesson_index < len(lessons):
        lessons[lesson_index]["status"] = "completed"
        _save(syllabus)
