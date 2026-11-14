"""Lesson/session state: what a session looks like in memory, how it's
created, and how it's rehydrated from the DB after a restart.

Nothing here talks to the Anthropic API — that's agent_calls.py, teacher.py,
quiz.py and lesson_plan.py. This file only owns the session's shape and
lifecycle, so any of those can change independently of it.
"""

import random
import uuid
from dataclasses import dataclass, field

import db
from agents import AGENTS_BY_KEY, CONNECTOR, DEEP_DIVER, POOL, SIMPLIFIER, STUDENT_DANI

JESTER_EVERY_MIN = 3
JESTER_EVERY_MAX = 4
HISTORY_WINDOW = 20

db.init_db()


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
    # Lesson plan (optional — only set for a "new lesson", never for "review"
    # sessions, which behave exactly as before this feature existed).
    plan: dict | None = None
    activity_index: int = 0
    autonomous_turns_used: int = 0
    awaiting_user: bool = True
    # In-memory only (not persisted): guards against re-delivering the
    # homework message if this process restarts right at the lesson's last
    # checkpoint and the student's answer is somehow replayed — an edge
    # case not worth a DB column for.
    homework_delivered: bool = False
    # Also in-memory only: whether the teacher has already explained the
    # CURRENT activity's material. Reset to False every time activity_index
    # advances (see lesson_plan.advance_after_checkpoint) — a plan-driven
    # activity always leads with the teacher actually teaching, never with
    # student chatter or a checkpoint question jumped straight to.
    activity_teacher_explained: bool = False

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
    topic: str, pool_keys: list | None = None, user_email: str | None = None, plan: dict | None = None
) -> Session:
    pool = resolve_pool(topic, pool_keys)
    # A lesson with a plan starts "mid-activity" (not yet waiting on the
    # student) so the classroom can open on its own, like a teacher who
    # walks in and starts teaching instead of standing there silently.
    session = Session(id=str(uuid.uuid4()), topic=topic, pool=pool, plan=plan, awaiting_user=not plan)
    SESSIONS[session.id] = session
    db.insert_lesson(
        session.id, session.topic,
        ",".join(a.key for a in session.pool),
        session.next_jester_round,
        user_email=user_email,
        plan=plan,
        awaiting_user=session.awaiting_user,
    )
    return session


def get_session(session_id: str) -> Session:
    if session_id in SESSIONS:
        return SESSIONS[session_id]

    # Not cached in this process (e.g. restarted, or a different Render instance) —
    # try to rehydrate it from the database before giving up.
    lesson = db.load_lesson(session_id)
    if not lesson:
        raise KeyError("session not found")

    pool_keys = lesson["pool_keys"].split(",")
    pool = [AGENTS_BY_KEY[k] for k in pool_keys if k in AGENTS_BY_KEY]
    session = Session(
        id=session_id,
        topic=lesson["topic"],
        pool=pool,
        round_count=lesson["round_count"],
        pool_turn_index=lesson["pool_turn_index"],
        next_jester_round=lesson["next_jester_round"],
        plan=lesson.get("plan"),
        activity_index=lesson.get("activity_index", 0),
        autonomous_turns_used=lesson.get("autonomous_turns_used", 0),
        awaiting_user=lesson.get("awaiting_user", True),
    )
    for row in db.load_messages(session_id):
        session.history.append(
            ChatMessage(row["agent_key"], row["display_name"], row["color"], row["content"])
        )
    SESSIONS[session_id] = session
    return session


def remember(session: Session, msg: ChatMessage):
    session.history.append(msg)
    db.insert_message(session.id, msg.agent_key, msg.display_name, msg.color, msg.content)
