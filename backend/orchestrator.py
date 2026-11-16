"""The one pipeline every lesson turn goes through.

What this replaces: two separately-maintained implementations of the same
turn (handle_user_message and handle_user_message_stream) that were supposed
to "mirror each other exactly" and did not — the non-streaming one never
implemented checkpoint feedback or plan advancement at all. Plus a third
hand-written state dispatch for autonomous beats in lesson_plan.py. Three
code paths, three separate re-derivations of where the lesson was.

Now there are two generators — one for "the student said something"
(user_message_events) and one for "the classroom moves on its own"
(autonomous_beat_events) — and every entry point consumes one of them:

    POST /api/message/stream   -> user_message_events, as SSE
    POST /api/message          -> user_message_events, drained to a list
    Slack                      -> user_message_events, drained to a list
    POST .../continue/stream   -> autonomous_beat_events, as SSE

Both generators are pure event producers: no time.sleep here, so the
non-streaming callers don't pay for pacing they never show. The SSE adapter
(main.py) does the pacing, keyed off "replay": True on a start event.

Each branch below maps 1:1 to one TeacherMode, so "what happens next" is
read off the state machine instead of re-derived from booleans.
"""

import random

import anthropic

from agent_calls import MissingApiKeyError, call_agent_stream
from agents import JESTER, TEACHER
from domain.teacher_actions import (
    AnswerQuestionAction,
    CheckpointFeedbackAction,
    ExplainAction,
    ReteachAction,
    run_action,
)
from domain.teacher_mode import TeacherMode
from session_state import (
    JESTER_EVERY_MAX,
    JESTER_EVERY_MIN,
    ChatMessage,
    Session,
    remember,
    repository,
)

API_KEY_MISSING_DETAIL = "לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑)."
API_KEY_INVALID_DETAIL = "מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב."
GENERIC_ERROR_DETAIL = "משהו השתבש בצד השרת. נסה שוב."

POOL_FALLBACK_TEXT = "(לא הצלחתי לנסח תגובה הפעם, נסה לנסח את השאלה מעט אחרת.)"


def _agent_fields(agent) -> dict:
    return {"key": agent.key, "name": agent.display_name, "color": agent.color}


def _say(session: Session, agent, text: str):
    """Emit an already-generated utterance and record it. 'replay': True
    tells the SSE adapter to pace this one word by word; a non-streaming
    caller ignores it."""
    yield {"type": "start", "replay": True, **_agent_fields(agent)}
    yield {"type": "token", "text": text}
    yield {"type": "end"}
    remember(session, ChatMessage(agent.key, agent.display_name, agent.color, text))


def _stream_agent(session: Session, agent, transcript: str, api_key: str | None):
    """Emit a live model stream from one of the pool agents (nobody but the
    teacher needs fact-verification, so there's nothing to hold back)."""
    yield {"type": "start", **_agent_fields(agent)}
    parts = []
    for chunk in call_agent_stream(agent, transcript, api_key=api_key):
        parts.append(chunk)
        yield {"type": "token", "text": chunk}
    yield {"type": "end"}
    text = "".join(parts).strip() or POOL_FALLBACK_TEXT
    remember(session, ChatMessage(agent.key, agent.display_name, agent.color, text))


def _next_pool_agent(session: Session):
    agent = session.pool[session.pool_turn_index % len(session.pool)]
    session.pool_turn_index += 1
    return agent


def _done(session: Session) -> dict:
    """The event the frontend's autoplay loop reads. Field names are the
    pre-rewrite contract on purpose — the frontend is untouched by this
    change — with teacher_mode added for the UI to use later."""
    lesson = session.lesson
    return {
        "type": "done",
        "continue": not lesson.autoplay_paused,
        "awaiting_user": lesson.autoplay_paused,
        "activity_index": lesson.activity_index,
        "teacher_mode": lesson.mode.value,
    }


def _mark_syllabus_lesson_completed(session: Session):
    """Report a finished lesson back to the syllabus it came from.

    This side effect used to live inside the lesson-advance code itself,
    which meant the "plan a lesson" module had to import the "plan a
    syllabus" module just to flip one status field. Coordinating two
    subsystems is the orchestrator's job, so it lives here — and a missing
    syllabus (e.g. a DB-less restart) must never break a working lesson."""
    if session.syllabus_id is None:
        return
    try:
        import syllabus

        syllabus.mark_lesson_completed(session.syllabus_id, session.syllabus_lesson_index)
    except KeyError:
        print(f"[orchestrator] syllabus {session.syllabus_id} is gone; lesson still completed standalone")


def _classroom_reacts(session: Session, api_key: str | None):
    """The pool agent whose turn it is responds, and the jester occasionally
    drops in — the classroom's reaction to whatever just happened."""
    yield from _stream_agent(session, _next_pool_agent(session), session.transcript_text(), api_key)
    if session.round_count >= session.next_jester_round:
        yield from _stream_agent(session, JESTER, session.transcript_text(), api_key)
        session.next_jester_round = session.round_count + random.randint(JESTER_EVERY_MIN, JESTER_EVERY_MAX)


def _guarded(generator_fn):
    """Errors have to be delivered as events, not raised: by the time an SSE
    generator runs, the HTTP 200 and headers are already on the wire, so an
    exception can't change the status code any more. The save in `finally`
    is what makes a client disconnect mid-stream (GeneratorExit) still
    persist the beats that already happened."""

    def wrapper(session: Session, *args, **kwargs):
        try:
            yield from generator_fn(session, *args, **kwargs)
        except MissingApiKeyError:
            yield {"type": "error", "detail": API_KEY_MISSING_DETAIL}
        except anthropic.AuthenticationError:
            yield {"type": "error", "detail": API_KEY_INVALID_DETAIL}
        except Exception as e:  # noqa: BLE001 — must not escape into a live stream
            print(f"[{generator_fn.__name__}] unexpected error: {e!r}")
            yield {"type": "error", "detail": GENERIC_ERROR_DETAIL}
        finally:
            repository.save(session)

    wrapper.__name__ = generator_fn.__name__
    return wrapper


@_guarded
def user_message_events(session: Session, user_text: str, api_key: str | None = None, image: dict | None = None):
    """One turn driven by something the student said.

    The fix that matters here: whether this message is treated as a
    checkpoint answer is decided by the state machine
    (lesson.expects_checkpoint_answer), not by a boolean combination
    re-derived at this call site. The old code advanced the lesson after
    *every* user message, so a student who asked a question mid-activity
    silently skipped the rest of that activity.
    """
    lesson = session.lesson
    display_text = user_text + (" 📎 [תמונה מצורפת]" if image else "")
    remember(session, ChatMessage("user", "את/ה", "#111827", display_text))
    session.round_count += 1

    if lesson.expects_checkpoint_answer:
        output = run_action(CheckpointFeedbackAction(), session, lesson, api_key=api_key)
        yield from _say(session, TEACHER, output.speech)

        lesson.record_checkpoint_result(output.understood)
        if not output.understood:
            # Stay on this activity: the next autonomous beat re-teaches it.
            # No pool-agent chatter — the student is mid-struggle.
            yield _done(session)
            return

        lesson.advance_to_next_activity()
        yield from _classroom_reacts(session, api_key)
        if lesson.should_deliver_homework():
            lesson.mark_homework_delivered()
            yield from _say(session, TEACHER, lesson.homework())
        if lesson.is_complete():
            _mark_syllabus_lesson_completed(session)
        yield _done(session)
        return

    # Not a checkpoint answer: an aside question, or any message in a
    # plan-less review session. Answer it without touching the lesson's
    # position — start/finish_answering_question restores the exact mode.
    lesson.start_answering_question()
    output = run_action(AnswerQuestionAction(image=image), session, lesson, api_key=api_key)
    yield from _say(session, TEACHER, output.speech)
    lesson.finish_answering_question()

    yield from _classroom_reacts(session, api_key)
    yield _done(session)


@_guarded
def autonomous_beat_events(session: Session, api_key: str | None = None):
    """One 'beat' of the classroom moving on its own, with no new user
    message. The frontend calls this in a loop while the previous beat's
    done event says continue=true.

    One branch per TeacherMode — adding a mode means adding a branch here,
    not editing a chain of boolean conditions.
    """
    lesson = session.lesson

    if lesson.autoplay_paused:
        # AWAITING_ANSWER (the student owes an answer) or COMPLETED.
        yield _done(session)
        return

    if lesson.mode is TeacherMode.TEACHING:
        output = run_action(ExplainAction(), session, lesson, api_key=api_key)
        yield from _say(session, TEACHER, output.speech)
        if output.board_notes:
            yield {"type": "board", "text": output.board_notes}
        lesson.finish_explaining()

    elif lesson.mode is TeacherMode.RETEACHING:
        output = run_action(ReteachAction(), session, lesson, api_key=api_key)
        yield from _say(session, TEACHER, output.speech)
        if output.board_notes:
            yield {"type": "board", "text": output.board_notes}
        lesson.retry_current_activity()

    elif lesson.mode is TeacherMode.DEMONSTRATING:
        activity = lesson.current_activity or {}
        transcript = session.transcript_text() + (
            f"\n\n[פעילות נוכחית במערך השיעור: {activity.get('title', '')} — {activity.get('summary', '')}]"
        )
        yield from _stream_agent(session, _next_pool_agent(session), transcript, api_key)
        lesson.record_autonomous_turn()

    elif lesson.mode is TeacherMode.ASKING_CHECKPOINT:
        # Static text from the approved plan — deliberately not run through
        # the fact-verification loop (see domain/teacher_actions.py).
        question = (lesson.current_activity or {}).get("checkpoint_question", "")
        yield from _say(session, TEACHER, question)
        lesson.mark_checkpoint_asked()

    yield _done(session)


def drain_to_messages(events) -> list:
    """Collect an event generator into the reply list the non-streaming
    callers (/api/message, Slack) return, so they run the same pipeline as
    the SSE route instead of their own copy of it."""
    replies = []
    current = None
    for event in events:
        kind = event.get("type")
        if kind == "start":
            current = {"key": event["key"], "name": event["name"], "color": event["color"], "parts": []}
        elif kind == "token" and current:
            current["parts"].append(event["text"])
        elif kind == "end" and current:
            replies.append(
                ChatMessage(current["key"], current["name"], current["color"], "".join(current["parts"]).strip())
            )
            current = None
        elif kind == "error":
            raise RuntimeError(event.get("detail", GENERIC_ERROR_DETAIL))
    return replies


def handle_user_message(session: Session, user_text: str, api_key: str | None = None, image: dict | None = None) -> list:
    """Non-streaming twin of the SSE route — the same pipeline, drained."""
    return drain_to_messages(user_message_events(session, user_text, api_key=api_key, image=image))
