"""Session state and turn orchestration for the virtual classroom."""

import json
import os
import random
import time
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
    QUIZ_SYSTEM_PROMPT,
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

db.init_db()


def _get_client(api_key: str | None) -> anthropic.Anthropic:
    """Every caller must bring its own Anthropic API key — there is no shared
    server-side key for the web chat. (The Slack integration is the one
    exception: it has no browser to hold a per-user key, so it supplies its
    own dedicated SLACK_ANTHROPIC_API_KEY explicitly — see slack_bot.py.)
    The key is used to build a one-off client for this call only; it is never
    logged, cached, or persisted to the DB."""
    if not api_key:
        raise MissingApiKeyError("No Anthropic API key was provided for this request.")
    return anthropic.Anthropic(api_key=api_key)


class MissingApiKeyError(Exception):
    pass


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

    def full_transcript_text(self):
        """Unlike transcript_text (windowed, used to keep per-turn prompts
        small), this includes the whole lesson — a quiz should be able to
        draw on anything discussed, not just the last few exchanges."""
        lines = [f"נושא השיעור: {self.topic}"]
        for m in self.history:
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


def create_session(topic: str, pool_keys: list | None = None, user_email: str | None = None) -> Session:
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
        user_email=user_email,
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

LATEX_INSTRUCTION = (
    "אם בתשובה שלך יש נוסחה מתמטית, כתוב אותה בפורמט LaTeX: נוסחה בתוך השורה בין $ $ "
    "(למשל $x^2+1$), ונוסחה בשורה נפרדת בין $$ $$. אל תשתמש בפורמט הזה לשום דבר חוץ מנוסחאות. "
)


def _build_user_content(text: str, image: dict | None):
    """Plain string when there's no image (unchanged, minimal request shape);
    a content-block list with an image block when there is one — only the
    teacher ever receives `image`, so it can actually look at what the
    student uploaded instead of just reading a '[image attached]' note."""
    if not image:
        return text
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": image["media_type"], "data": image["data"]},
        },
        {"type": "text", "text": text},
    ]


def _call_agent(
    agent, transcript: str, extra_instruction: str = "", api_key: str | None = None, image: dict | None = None
) -> str:
    user_text = (
        f"{transcript}\n\n"
        f"הגב כעת כ-{agent.display_name}, בהתאם לכללים שלך. "
        f"{extra_instruction}"
        f"{LATEX_INSTRUCTION}"
        "כתוב רק את התגובה שלך, בלי לציין את שמך."
    )
    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=agent.system_prompt,
        messages=[{"role": "user", "content": _build_user_content(user_text, image)}],
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


def _call_agent_stream(agent, transcript: str, api_key: str | None = None):
    """Like _call_agent, but yields text deltas as they arrive from the model
    instead of waiting for the full response. Used for agents that don't need
    verification (everyone except the teacher), where there's no reason to
    hold text back from the user."""
    user_content = (
        f"{transcript}\n\n"
        f"הגב כעת כ-{agent.display_name}, בהתאם לכללים שלך. "
        f"{LATEX_INSTRUCTION}"
        "כתוב רק את התגובה שלך, בלי לציין את שמך."
    )
    with _get_client(api_key).messages.stream(
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=agent.system_prompt,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _word_chunks(text: str):
    """Split already-generated text into word-sized pieces so it can be
    'replayed' to the client incrementally — used for the teacher's answer,
    which must be fully generated and verified before any of it is shown."""
    parts = text.split(" ")
    for i, part in enumerate(parts):
        yield part + (" " if i < len(parts) - 1 else "")


def _verify_teacher_answer(topic: str, answer: str, api_key: str | None = None) -> tuple[bool, str]:
    verify_prompt = f"נושא: {topic}\n\nתשובת המורה:\n{answer}"
    response = _get_client(api_key).messages.create(
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


def _get_validated_teacher_reply(session: Session, api_key: str | None = None, image: dict | None = None) -> str:
    transcript = session.transcript_text()
    answer = _call_agent(TEACHER, transcript, api_key=api_key, image=image)
    for _ in range(MAX_VERIFY_RETRIES):
        ok, reason = _verify_teacher_answer(session.topic, answer, api_key=api_key)
        if ok:
            return answer
        answer = _call_agent(
            TEACHER,
            transcript,
            extra_instruction=(
                f"שים לב: הניסיון הקודם שלך הכיל טעות עובדתית ({reason}). "
                "תקן אותה בתשובה הבאה. "
            ),
            api_key=api_key,
            image=image,
        )
    return answer


def _remember(session: Session, msg: ChatMessage):
    session.history.append(msg)
    db.insert_message(session.id, msg.agent_key, msg.display_name, msg.color, msg.content)


def handle_user_message(
    session: Session, user_text: str, api_key: str | None = None, image: dict | None = None
) -> list:
    display_text = user_text + (" 📎 [תמונה מצורפת]" if image else "")
    _remember(session, ChatMessage("user", "את/ה", "#111827", display_text))
    session.round_count += 1

    replies = []

    teacher_text = _get_validated_teacher_reply(session, api_key=api_key, image=image)
    teacher_msg = ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, teacher_text)
    _remember(session, teacher_msg)
    replies.append(teacher_msg)

    pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
    session.pool_turn_index += 1
    pool_text = _call_agent(pool_agent, session.transcript_text(), api_key=api_key)
    pool_msg = ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, pool_text)
    _remember(session, pool_msg)
    replies.append(pool_msg)

    if session.round_count >= session.next_jester_round:
        jester_text = _call_agent(JESTER, session.transcript_text(), api_key=api_key)
        jester_msg = ChatMessage(JESTER.key, JESTER.display_name, JESTER.color, jester_text)
        _remember(session, jester_msg)
        replies.append(jester_msg)
        session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)

    db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)
    return replies


TEACHER_REPLAY_DELAY = 0.02  # seconds between words when "replaying" the already-verified teacher answer


def handle_user_message_stream(
    session: Session, user_text: str, api_key: str | None = None, image: dict | None = None
):
    """Generator of dict events for incremental (SSE) delivery to the browser:
    {"type": "start", "key", "name", "color"} / {"type": "token", "text"} /
    {"type": "end"} per agent reply, then a final {"type": "done"}.

    Mirrors handle_user_message's logic exactly (teacher verification loop,
    pool rotation, jester cameo, DB writes) — this is the streaming twin of
    that function, not a separate code path with its own rules.

    The teacher's answer can't be streamed live token-by-token: it has to be
    fully generated and pass the silent verification/retry loop before any
    of it is safe to show (an answer that gets corrected mid-stream can't be
    un-said). So its already-complete, already-validated text is "replayed"
    to the client word by word instead — still a real incremental HTTP
    stream, just not a live model stream. Every other agent streams live.

    Any error (missing/invalid key, model/network failure) is caught and
    emitted as a {"type": "error"} event rather than raised, because by the
    time this generator runs the HTTP 200 + SSE headers have already been
    sent — an exception here can't change the status code anymore.
    """
    try:
        display_text = user_text + (" 📎 [תמונה מצורפת]" if image else "")
        _remember(session, ChatMessage("user", "את/ה", "#111827", display_text))
        session.round_count += 1

        # --- Teacher: verify silently, then replay the validated text ---
        teacher_text = _get_validated_teacher_reply(session, api_key=api_key, image=image)
        yield {"type": "start", "key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color}
        for chunk in _word_chunks(teacher_text):
            yield {"type": "token", "text": chunk}
            time.sleep(TEACHER_REPLAY_DELAY)
        yield {"type": "end"}
        teacher_msg = ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, teacher_text)
        _remember(session, teacher_msg)

        # --- Pool agent: live model stream ---
        pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
        session.pool_turn_index += 1
        yield {"type": "start", "key": pool_agent.key, "name": pool_agent.display_name, "color": pool_agent.color}
        parts = []
        for chunk in _call_agent_stream(pool_agent, session.transcript_text(), api_key=api_key):
            parts.append(chunk)
            yield {"type": "token", "text": chunk}
        pool_text = "".join(parts).strip() or "(לא הצלחתי לנסח תגובה הפעם, נסה לנסח את השאלה מעט אחרת.)"
        yield {"type": "end"}
        pool_msg = ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, pool_text)
        _remember(session, pool_msg)

        # --- Jester cameo: live model stream, rare rounds only ---
        if session.round_count >= session.next_jester_round:
            yield {"type": "start", "key": JESTER.key, "name": JESTER.display_name, "color": JESTER.color}
            parts = []
            for chunk in _call_agent_stream(JESTER, session.transcript_text(), api_key=api_key):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            jester_text = "".join(parts).strip() or "..."
            yield {"type": "end"}
            jester_msg = ChatMessage(JESTER.key, JESTER.display_name, JESTER.color, jester_text)
            _remember(session, jester_msg)
            session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)

        db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)
        yield {"type": "done"}

    except MissingApiKeyError:
        yield {"type": "error", "detail": "לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑)."}
    except anthropic.AuthenticationError:
        yield {"type": "error", "detail": "מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב."}
    except Exception as e:
        print(f"[handle_user_message_stream] unexpected error: {e!r}")
        yield {"type": "error", "detail": "משהו השתבש בצד השרת. נסה שוב."}


QUIZ_MODEL = os.environ.get("CLASSROOM_QUIZ_MODEL", MODEL)
QUIZ_MAX_TOKENS = 1500
QUIZ_MAX_RETRIES = 2


class QuizGenerationError(Exception):
    pass


def _extract_json_array(raw: str):
    """The model is instructed to return raw JSON, but models occasionally
    wrap it in a ```json code fence anyway — strip that defensively before
    parsing instead of failing the whole quiz over a formatting slip."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def generate_quiz(session: Session, api_key: str | None = None) -> list:
    user_content = session.full_transcript_text()
    last_error = None
    for _ in range(QUIZ_MAX_RETRIES):
        response = _get_client(api_key).messages.create(
            model=QUIZ_MODEL,
            max_tokens=QUIZ_MAX_TOKENS,
            system=QUIZ_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            questions = _extract_json_array(raw)
            if not isinstance(questions, list) or not questions:
                raise ValueError("expected a non-empty JSON array")
            for q in questions:
                if not (isinstance(q.get("options"), list) and len(q["options"]) >= 2):
                    raise ValueError("question missing valid options")
                if not isinstance(q.get("correct_index"), int):
                    raise ValueError("question missing correct_index")
            return questions
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            last_error = e
            print(f"[generate_quiz] malformed quiz JSON, retrying: {e}; raw={raw[:300]!r}")

    raise QuizGenerationError(f"לא הצלחתי לבנות בוחן תקין: {last_error}")
