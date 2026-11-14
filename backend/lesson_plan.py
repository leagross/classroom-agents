"""Everything specific to a plan-driven lesson: generating the plan itself
(goals + activities, approved/regenerated before any session exists), and
advancing a session through it one autonomous "beat" at a time.

A "review" session never touches this module — session.plan is just None
and the rest of the app (orchestrator.py) behaves exactly as it did before
this feature existed.
"""

import json
import os
import time

import anthropic

import db
from agent_calls import (
    MODEL,
    MissingApiKeyError,
    TEACHER_REPLAY_DELAY,
    call_agent_stream,
    get_client,
    word_chunks,
)
from agents import LESSON_PLAN_SYSTEM_PROMPT, TEACHER
from json_utils import extract_json
from session_state import ChatMessage, Session, remember
from teacher import get_validated_teacher_explanation

LESSON_PLAN_MODEL = os.environ.get("CLASSROOM_LESSON_PLAN_MODEL", MODEL)
# Hebrew text tokenizes far less efficiently than English, and a 3-5 activity
# plan (title + summary + checkpoint_question each, plus JSON overhead) can
# run well past 1500 tokens — too low a budget here doesn't fail cleanly, it
# truncates mid-string and surfaces as a confusing "Unterminated string" JSON
# parse error instead of a clear "response was cut off".
LESSON_PLAN_MAX_TOKENS = 3000
LESSON_PLAN_MAX_RETRIES = 2
DEFAULT_AUTONOMOUS_EXCHANGES = 1


class LessonPlanGenerationError(Exception):
    pass


def generate_lesson_plan(topic: str, pool: list, api_key: str | None = None) -> dict:
    """A lesson plan is generated once, as a preview the user can approve or
    regenerate, before any session/DB row exists — same spirit as
    generate_quiz, just earlier in the lifecycle and shaped as an object
    instead of an array."""
    pool_names = ", ".join(a.display_name for a in pool)
    user_content = f"נושא השיעור: {topic}\nהתלמידים שישתתפו: {pool_names}"
    last_error = None
    for _ in range(LESSON_PLAN_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=LESSON_PLAN_MODEL,
            max_tokens=LESSON_PLAN_MAX_TOKENS,
            system=LESSON_PLAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "max_tokens":
            print(f"[generate_lesson_plan] response truncated at max_tokens={LESSON_PLAN_MAX_TOKENS}; raw_len={len(raw)}")
        try:
            plan = extract_json(raw)
            if not isinstance(plan, dict):
                raise ValueError("expected a JSON object")
            if not (isinstance(plan.get("goals"), list) and plan["goals"]):
                raise ValueError("missing goals")
            activities = plan.get("activities")
            if not (isinstance(activities, list) and activities):
                raise ValueError("missing activities")
            for a in activities:
                if not (isinstance(a.get("title"), str) and a["title"]):
                    raise ValueError("activity missing title")
                if not isinstance(a.get("checkpoint_question"), str):
                    raise ValueError("activity missing checkpoint_question")
                if not (isinstance(a.get("stage"), str) and a["stage"]):
                    raise ValueError("activity missing stage")
                raw_exchanges = a.get("autonomous_exchanges")
                a["autonomous_exchanges"] = int(raw_exchanges) if raw_exchanges is not None else DEFAULT_AUTONOMOUS_EXCHANGES
            # Homework is a nice-to-have, not core to the classroom's
            # mechanics — default it instead of spending a retry over it.
            if not isinstance(plan.get("homework"), str):
                plan["homework"] = ""
            return plan
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError) as e:
            last_error = e
            print(f"[generate_lesson_plan] malformed plan JSON, retrying: {e}; raw={raw[:300]!r}")

    raise LessonPlanGenerationError(f"לא הצלחתי לבנות מערך שיעור תקין: {last_error}")


def advance_lesson_stream(session: Session, api_key: str | None = None):
    """Generator (same SSE event shape as orchestrator.handle_user_message_stream)
    that produces exactly ONE autonomous 'beat' of a plan-driven lesson,
    without any new user message: the teacher explaining the activity's
    material (always first — never skipped), a pool-agent reaction (the
    classroom talking amongst itself, only once the teacher has actually
    taught this activity), or, once the autonomous budget is spent, the
    teacher's pre-written checkpoint question — at which point the lesson
    pauses and waits for the real student again.

    The frontend calls this in a loop (with a short delay between calls, for
    pacing) while the previous call's "done" event says continue=true.
    """
    try:
        if not session.plan:
            yield {"type": "done", "continue": False, "awaiting_user": True}
            return

        activities = session.plan.get("activities", [])
        if session.activity_index >= len(activities):
            session.awaiting_user = True
            db.update_lesson_plan_state(session.id, session.activity_index, session.autonomous_turns_used, True)
            yield {"type": "done", "continue": False, "awaiting_user": True}
            return

        activity = activities[session.activity_index]

        if not session.activity_teacher_explained:
            # The teacher always teaches the material first — no jumping
            # straight to student chatter or a checkpoint question.
            explanation = get_validated_teacher_explanation(session, activity, api_key=api_key)
            yield {"type": "start", "key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color}
            for chunk in word_chunks(explanation):
                yield {"type": "token", "text": chunk}
                time.sleep(TEACHER_REPLAY_DELAY)
            yield {"type": "end"}
            remember(session, ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, explanation))

            session.activity_teacher_explained = True
            yield {"type": "done", "continue": True, "awaiting_user": False, "activity_index": session.activity_index}
            return

        budget = activity.get("autonomous_exchanges", DEFAULT_AUTONOMOUS_EXCHANGES)

        if session.autonomous_turns_used < budget:
            # The classroom talks amongst itself: the pool agent whose turn
            # it is reacts to the activity and what's been said so far.
            pool_agent = session.pool[session.pool_turn_index % len(session.pool)]
            session.pool_turn_index += 1
            transcript = session.transcript_text() + f"\n\n[פעילות נוכחית במערך השיעור: {activity['title']} — {activity.get('summary', '')}]"
            yield {"type": "start", "key": pool_agent.key, "name": pool_agent.display_name, "color": pool_agent.color}
            parts = []
            for chunk in call_agent_stream(pool_agent, transcript, api_key=api_key):
                parts.append(chunk)
                yield {"type": "token", "text": chunk}
            text = "".join(parts).strip() or "..."
            yield {"type": "end"}
            remember(session, ChatMessage(pool_agent.key, pool_agent.display_name, pool_agent.color, text))

            session.autonomous_turns_used += 1
            db.update_lesson_plan_state(session.id, session.activity_index, session.autonomous_turns_used, False)
            yield {"type": "done", "continue": True, "awaiting_user": False, "activity_index": session.activity_index}
        else:
            # Budget spent — the teacher asks the activity's pre-written
            # checkpoint question (no extra model call needed for this one;
            # it was already written when the plan was generated) and the
            # lesson pauses for the real student.
            question = activity["checkpoint_question"]
            yield {"type": "start", "key": TEACHER.key, "name": TEACHER.display_name, "color": TEACHER.color}
            for chunk in word_chunks(question):
                yield {"type": "token", "text": chunk}
                time.sleep(TEACHER_REPLAY_DELAY)
            yield {"type": "end"}
            remember(session, ChatMessage(TEACHER.key, TEACHER.display_name, TEACHER.color, question))

            session.awaiting_user = True
            db.update_lesson_plan_state(session.id, session.activity_index, session.autonomous_turns_used, True)
            yield {"type": "done", "continue": False, "awaiting_user": True, "activity_index": session.activity_index}

    except MissingApiKeyError:
        yield {"type": "error", "detail": "לא סופק מפתח API. הזן את מפתח ה-Anthropic האישי שלך בהגדרות (🔑)."}
    except anthropic.AuthenticationError:
        yield {"type": "error", "detail": "מפתח ה-API שהזנת לא תקין. בדוק אותו בהגדרות ונסה שוב."}
    except Exception as e:
        print(f"[advance_lesson_stream] unexpected error: {e!r}")
        yield {"type": "error", "detail": "משהו השתבש בצד השרת. נסה שוב."}


def advance_after_checkpoint(session: Session) -> dict:
    """Called once a real student has answered the current activity's
    checkpoint question (i.e. after a normal user message in a plan-driven
    lesson). Moves on to the next activity and returns the extra fields the
    SSE "done" event should carry so the frontend knows whether to resume
    advance_lesson_stream's loop. Returns {} for a plan-less ("review")
    session — orchestrator.py doesn't need to know the difference.

    If this move exhausts the plan (the "summary" activity was just
    answered) and the plan has homework, the extra dict also carries
    {"homework": "..."} exactly once — orchestrator.py is responsible for
    turning that into an actual teacher message in the stream, since
    rendering it isn't this module's job."""
    if not session.plan:
        return {}
    activities = session.plan.get("activities", [])
    session.activity_index += 1
    session.autonomous_turns_used = 0
    session.activity_teacher_explained = False
    more_activities_left = session.activity_index < len(activities)
    session.awaiting_user = not more_activities_left
    db.update_lesson_plan_state(
        session.id, session.activity_index, session.autonomous_turns_used, session.awaiting_user
    )
    extra = {
        "continue": more_activities_left,
        "awaiting_user": session.awaiting_user,
        "activity_index": session.activity_index,
    }
    homework = session.plan.get("homework")
    if not more_activities_left and homework and not session.homework_delivered:
        session.homework_delivered = True
        extra["homework"] = homework
    return extra
