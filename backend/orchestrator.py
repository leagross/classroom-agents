"""Turn orchestration for a single user message: the teacher's verified
reply, the pool agent's reaction, and a rare jester cameo.

This is the "review" lesson's entire behavior, unchanged since before the
lesson-plan feature existed. For a plan-driven lesson, the only extra thing
that happens here is handing off to lesson_plan.advance_after_checkpoint at
the very end, so the frontend knows whether to resume the autonomous loop —
everything about *what* that means lives in lesson_plan.py, not here.
"""

import random
import time

import anthropic

from agent_calls import MissingApiKeyError, TEACHER_REPLAY_DELAY, call_agent, call_agent_stream, word_chunks
from agents import JESTER, TEACHER
from lesson_plan import advance_after_checkpoint, retry_after_misunderstanding
from session_state import ChatMessage, JESTER_EVERY_MAX, JESTER_EVERY_MIN, Session, remember
from teacher import get_validated_checkpoint_feedback, get_validated_teacher_reply

import db


def handle_user_message(
    session: Session, user_text: str, api_key: str | None = None, image: dict | None = None
) -> list:
    display_text = user_text + (" 📎 [תמונה מצורפת]" if image else "")
    remember(session, ChatMessage("user", "את/ה", "#111827", display_text))
    session.round_count += 1

    replies = []

    teacher_text = get_validated_teacher_reply(session, api_key=api_key, image=image)
    teacher_msg = ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, teacher_text)
    remember(session, teacher_msg)
    replies.append(teacher_msg)

    pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
    session.pool_turn_index += 1
    pool_text = call_agent(pool_agent, session.transcript_text(), api_key=api_key)
    pool_msg = ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, pool_text)
    remember(session, pool_msg)
    replies.append(pool_msg)

    if session.round_count >= session.next_jester_round:
        jester_text = call_agent(JESTER, session.transcript_text(), api_key=api_key)
        jester_msg = ChatMessage(JESTER.key, JESTER.display_name, JESTER.color, jester_text)
        remember(session, jester_msg)
        replies.append(jester_msg)
        session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)

    db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)
    return replies


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
        remember(session, ChatMessage("user", "את/ה", "#111827", display_text))
        session.round_count += 1

        # If this message answers the current activity's checkpoint question
        # (plan-driven lesson, was actually waiting on the student, AND
        # there's still an activity at activity_index — once the plan is
        # exhausted, activity_index points past the end of the list, but
        # awaiting_user stays true forever after homework is delivered), the
        # teacher's reply is a comprehension check, not a generic answer —
        # and its verdict decides whether the lesson is allowed to move on.
        answering_checkpoint = (
            bool(session.plan)
            and session.awaiting_user
            and session.activity_index < len(session.plan.get("activities", []))
        )
        understood = True

        # --- Teacher: verify silently, then replay the validated text ---
        if answering_checkpoint:
            activity = session.plan["activities"][session.activity_index]
            teacher_text, understood = get_validated_checkpoint_feedback(session, activity, api_key=api_key)
        else:
            teacher_text = get_validated_teacher_reply(session, api_key=api_key, image=image)
        yield {"type": "start", "key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color}
        for chunk in word_chunks(teacher_text):
            yield {"type": "token", "text": chunk}
            time.sleep(TEACHER_REPLAY_DELAY)
        yield {"type": "end"}
        teacher_msg = ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, teacher_text)
        remember(session, teacher_msg)

        if answering_checkpoint and not understood:
            # Stay on this activity — skip the pool agent/jester this turn
            # and let the autonomous loop re-teach it instead of moving on.
            db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)
            yield {"type": "done", **retry_after_misunderstanding(session)}
            return

        # --- Pool agent: live model stream ---
        pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
        session.pool_turn_index += 1
        yield {"type": "start", "key": pool_agent.key, "name": pool_agent.display_name, "color": pool_agent.color}
        parts = []
        for chunk in call_agent_stream(pool_agent, session.transcript_text(), api_key=api_key):
            parts.append(chunk)
            yield {"type": "token", "text": chunk}
        pool_text = "".join(parts).strip() or "(לא הצלחתי לנסח תגובה הפעם, נסה לנסח את השאלה מעט אחרת.)"
        yield {"type": "end"}
        pool_msg = ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, pool_text)
        remember(session, pool_msg)

        # --- Jester cameo: live model stream, rare rounds only ---
        if session.round_count >= session.next_jester_round:
            yield {"type": "start", "key": JESTER.key, "name": JESTER.display_name, "color": JESTER.color}
            parts = []
            for chunk in call_agent_stream(JESTER, session.transcript_text(), api_key=api_key):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            jester_text = "".join(parts).strip() or "..."
            yield {"type": "end"}
            jester_msg = ChatMessage(JESTER.key, JESTER.display_name, JESTER.color, jester_text)
            remember(session, jester_msg)
            session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)

        db.update_lesson_state(session.id, session.round_count, session.pool_turn_index, session.next_jester_round)

        # No-op ({}) for a plan-less "review" session — see lesson_plan.py.
        extra = advance_after_checkpoint(session)

        # If the plan just ended with homework to hand out, that's delivered
        # as one more teacher message (replayed like the checkpoint question,
        # since it's pre-written text, not a live model call) before "done".
        homework = extra.pop("homework", None)
        if homework:
            yield {"type": "start", "key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color}
            for chunk in word_chunks(homework):
                yield {"type": "token", "text": chunk}
                time.sleep(TEACHER_REPLAY_DELAY)
            yield {"type": "end"}
            remember(session, ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, homework))

        yield {"type": "done", **extra}

    except MissingApiKeyError:
        yield {"type": "error", "detail": "לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑)."}
    except anthropic.AuthenticationError:
        yield {"type": "error", "detail": "מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב."}
    except Exception as e:
        print(f"[handle_user_message_stream] unexpected error: {e!r}")
        yield {"type": "error", "detail": "משהו השתבש בצד השרת. נסה שוב."}
