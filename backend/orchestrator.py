"""Session state and turn orchestration for the virtual classroom."""

import os
import random
import uuid
from dataclasses import dataclass, field

import anthropic

import db
from agents import (
    AGENTS_BY_KEY,
    CONNECTOR,
    DEEP_DIVER,
    JESTER,
    POOL,
    SIMPLIFIER,
    STUDENT_DANI,
    TEACHER,
    VERIFIER_SYSTEM_PROMPT,
)

MODEL = os.environ.get("CLASSROOM_MODEL", "claude-sonnet-5-5")
VERIFIER_MODEL = os.environ.get("CLASSROOM_VERIFIER_MODEL", "claude-haiku-5-5")
MAX_VERIFY_RETRIES = 2
JESTER_EVERY_MIN = 3
JESTER_EVERY_MAX = 4
HISTORY_WINDOW = 20

_client = anthropic.Anthropic()
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

    def transcript_text(self):
        lines = [f"נושא השיעור: {self.topic}"]
        for m in self.history[-HISTORY_WINDOW:]:
            lines.append(f"{m.display_name}: {m.content}")
        return "\n".join(lines)


SESSIONS = {}

TECHNICAL_KEYWORDS = [
    "מתמטיקה", "פיזיקה", "כימיה", "אלגברה", "חדו\"א", "נוסחה", "משוואה",
    "קוד", "תכנות", "אלגוריתם", "ביולוגיה", "סטטיסטיקה",
]
NARRATIVE_KEYWORDS = [
    "היסטוריה", "ערכים", "ספרות", "פילוסופיה", "חברה", "פסיכולוגיה", "אתיקה", "תנ\"ך",
]


def choose_pool(topic: str):
    t = topic.lower()
    if any(k in topic for k in TECHNICAL_KEYWORDS):
        return [DEEP_DIVER, SIMPLIFIER]
    if any(k in topic for k in NARRATIVE_KEYWORDS):
        return [STUDENT_DANI, CONNECTOR]
    return random.sample(POOL, 2)


def create_session(topic: str, pool_keys: list | None = None) -> Session:
    if pool_keys:
        pool = [AGENTS_BY_KEY[k] for k in pool_keys if k in AGENTS_BY_KEY and AGENTS_BY_KEY[k] in POOL]
        if len(pool) != 2:
            raise ValueError("pool_keys must name exactly 2 valid pool agents")
    else:
        pool = choose_pool(topic)
    session = Session(id=str(uuid.uuid4()), topic=topic, pool=pool)
    SESSIONS[session.id] = session
    db.insert_lesson(
        session.id, session.topic,
        ",".join(a.key for a in session.pool),
        session.next_jester_round,
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
    )
    for row in db.load_messages(session_id):
        session.history.append(
            ChatMessage(row["agent_key"], row["display_name"], row["color"], row["content"])
        )
    SESSIONS[session_id] = session
    return session


AGENT_MAX_TOKENS = 1024
VERIFIER_MAX_TOKENS = 300


def _call_agent(agent, transcript: str, extra_instruction: str = "") -> str:
    user_content = (
        f"{transcript}\n\n"
        f"הגב כעת כ-{agent.display_name}, בהתאם לכללים שלך. "
        f"{extra_instruction}"
        "כתוב רק את התגובה שלך, בלי לציין את שמך."
    )
    response = _client.messages.create(
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=agent.system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    block_types = [b.type for b in response.content]
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    print(
        f"[_call_agent] agent={agent.key} stop_reason={response.stop_reason} "
        f"blocks={block_types} usage={response.usage} text_len={len(text)}"
    )
    if not text:
        # Defensive fallback: an empty reply (e.g. truncated generation) must never
        # be fed back into the transcript, since that poisons later turns.
        text = "(לא הצלחתי לנסח תגובה הפעם, נסה לנסח את השאלה מעט אחרת.)"
    return text


def _verify_teacher_answer(topic: str, answer: str) -> tuple[bool, str]:
    verify_prompt = f"נושא: {topic}\n\nתשובת המורה:\n{answer}"
    response = _client.messages.create(
        model=VERIFIER_MODEL,
        max_tokens=VERIFIER_MAX_TOKENS,
        system=VERIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": verify_prompt}],
    )
    verdict = "".join(block.text for block in response.content if block.type == "text").strip()
    if not verdict or verdict.startswith("תקין"):
        # Treat an empty/unparseable verdict as "pass" rather than looping forever.
        return True, ""
    return False, verdict


def _get_validated_teacher_reply(session: Session) -> str:
    transcript = session.transcript_text()
    answer = _call_agent(TEACHER, transcript)
    for _ in range(MAX_VERIFY_RETRIES):
        ok, reason = _verify_teacher_answer(session.topic, answer)
        if ok:
            return answer
        answer = _call_agent(
            TEACHER,
            transcript,
            extra_instruction=(
                f"שים לב: הניסיון הקודם שלך הכיל טעות עובדתית ({reason}). "
                "תקן אותה בתשובה הבאה. "
            ),
        )
    return answer


def _remember(session: Session, msg: ChatMessage):
    session.history.append(msg)
    db.insert_message(session.id, msg.agent_key, msg.display_name, msg.color, msg.content)


def handle_user_message(session: Session, user_text: str) -> list:
    _remember(session, ChatMessage("user", "את/ה", "#111827", user_text))
    session.round_count += 1

    replies = []

    teacher_text = _get_validated_teacher_reply(session)
    teacher_msg = ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, teacher_text)
    _remember(session, teacher_msg)
    replies.append(teacher_msg)

    pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
    session.pool_turn_index += 1
    pool_text = _call_agent(pool_agent, session.transcript_text())
    pool_msg = ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, pool_text)
    _remember(session, pool_msg)
    replies.append(pool_msg)

    if session.round_count >= session.next_jester_round:
        jester_text = _call_agent(JESTER, session.transcript_text())
        jester_msg = ChatMessage(JESTER.key, JESTER.display_name, JESTER.color, jester_text)
        _remember(session, jester_msg)
        replies.append(jester_msg)
        session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)

    db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)
    return replies
