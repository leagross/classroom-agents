"""Session: who is in the room, what was said, and (via Session.lesson) where
the lesson is.

What changed in the rewrite: the six loose plan fields that used to live
here (plan, activity_index, autonomous_turns_used, awaiting_user,
homework_delivered, activity_teacher_explained) are gone. They are now one
Lesson object (domain/lesson.py) that owns its own state machine, so no
other module reads or flips those flags directly. Persistence goes through
SessionRepository, not inline db.update_* calls.
"""

import random
import uuid
from dataclasses import dataclass, field

import db
from agents import AGENTS_BY_KEY, CONNECTOR, DEEP_DIVER, POOL, SIMPLIFIER, STUDENT_DANI
from domain.lesson import Lesson
from services.session_repository import SessionRepository, lesson_from_row

JESTER_EVERY_MIN = 3
JESTER_EVERY_MAX = 4
HISTORY_WINDOW = 20

db.init_db()

repository = SessionRepository()


@dataclass
class ChatMessage:
    agent_key: str
    display_name: str
    color: str
    content: str


@dataclass
class Session:
    id: str
    topic: str
    pool: list
    history: list = field(default_factory=list)  # list[ChatMessage]
    round_count: int = 0
    next_jester_round: int = field(default_factory=lambda: random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX))
    pool_turn_index: int = 0
    # The lesson's state machine. A "review" session gets a plan-less Lesson,
    # which reports is_complete() and sits in COMPLETED — so the orchestrator
    # needs no special case for "this session has no plan".
    lesson: Lesson = field(default_factory=Lesson)
    # Set only when this session was started from a syllabus lesson.
    syllabus_id: str | None = None
    syllabus_lesson_index: int | None = None

    def transcript_text(self):
        lines = [f"נושא השיעור: {self.topic}"]
        for m in self.history[-HISTORY_WINDOW:]:
            lines.append(f"{m.display_name}: {m.content}")
        return "\n".join(lines)

    def full_transcript_text(self):
        """Unlike transcript_text (windowed, used to keep per-turn prompts
        small), this includes the whole lesson — a quiz should be able to
        draw on anything discussed, not just the last few exchanges."""
        lines = [f"נושא השיעור: {self.topic}"]
        for m in self.history:
            lines.append(f"{m.display_name}: {m.content}")
        return "\n".join(lines)


SESSIONS: dict[str, Session] = {}

TECHNICAL_KEYWORDS = [
    "מתמטיקה", "פיזיקה", "כימיה", "אלגברה", "חדו\"א", "נוסחה", "משוואה",
    "קוד", "תכנות", "אלגוריתם", "ביולוגיה", "סטטיסטיקה",
]
NARRATIVE_KEYWORDS = [
    "היסטוריה", "ערכים", "ספרות", "פילוסופיה", "חברה", "פסיכולוגיה", "אתיקה", "תנ\"ך",
]


def choose_pool(topic: str):
    if any(k in topic for k in TECHNICAL_KEYWORDS):
        return [DEEP_DIVER, SIMPLIFIER]
    if any(k in topic for k in NARRATIVE_KEYWORDS):
        return [STUDENT_DANI, CONNECTOR]
    return random.sample(POOL, 2)


def resolve_pool(topic: str, pool_keys: list | None = None) -> list:
    if pool_keys:
        pool = [AGENTS_BY_KEY[k] for k in pool_keys if k in AGENTS_BY_KEY and AGENTS_BY_KEY[k] in POOL]
        if len(pool) != 2:
            raise ValueError("pool_keys must name exactly 2 valid pool agents")
        return pool
    return choose_pool(topic)


def create_session(
    topic: str,
    pool_keys: list | None = None,
    user_email: str | None = None,
    plan: dict | None = None,
    syllabus_id: str | None = None,
    syllabus_lesson_index: int | None = None,
) -> Session:
    pool = resolve_pool(topic, pool_keys)
    # A lesson with a plan opens in TEACHING, so the classroom starts
    # teaching on its own instead of standing there waiting for the student
    # to speak first; a plan-less review session opens COMPLETED (nothing
    # scripted to advance through) and just answers whatever comes.
    session = Session(
        id=str(uuid.uuid4()), topic=topic, pool=pool, lesson=Lesson(plan=plan),
        syllabus_id=syllabus_id, syllabus_lesson_index=syllabus_lesson_index,
    )
    SESSIONS[session.id] = session
    db.insert_lesson(
        session.id, session.topic,
        ",".join(a.key for a in session.pool),
        session.next_jester_round,
        user_email=user_email,
        plan=plan,
        awaiting_user=session.lesson.autoplay_paused,
        syllabus_id=syllabus_id,
        syllabus_lesson_index=syllabus_lesson_index,
    )
    repository.save(session)
    return session


def get_session(session_id: str) -> Session:
    if session_id in SESSIONS:
        return SESSIONS[session_id]

    # Not cached in this process (e.g. restarted, or a different Render instance) —
    # try to rehydrate it from the database before giving up.
    row = repository.load_row(session_id)
    if not row:
        raise KeyError("session not found")

    pool_keys = row["pool_keys"].split(",")
    pool = [AGENTS_BY_KEY[k] for k in pool_keys if k in AGENTS_BY_KEY]
    session = Session(
        id=session_id,
        topic=row["topic"],
        pool=pool,
        round_count=row["round_count"],
        pool_turn_index=row["pool_turn_index"],
        next_jester_round=row["next_jester_round"],
        lesson=lesson_from_row(row),
        syllabus_id=row.get("syllabus_id"),
        syllabus_lesson_index=row.get("syllabus_lesson_index"),
    )
    for msg_row in repository.load_messages(session_id):
        session.history.append(
            ChatMessage(msg_row["agent_key"], msg_row["display_name"], msg_row["color"], msg_row["content"])
        )
    SESSIONS[session_id] = session
    return session


def remember(session: Session, msg: ChatMessage):
    session.history.append(msg)
    repository.add_message(session.id, msg)


def delete_session(session_id: str):
    SESSIONS.pop(session_id, None)
    db.delete_lesson(session_id)
