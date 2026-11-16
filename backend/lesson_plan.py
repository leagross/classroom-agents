"""Generating a lesson plan: goals + 5 staged activities + homework,
produced as a preview the user approves or regenerates before any session
exists.

Advancing a lesson through that plan is NOT here any more — that state
machine lives in domain/lesson.py and is driven by
orchestrator.autonomous_beat_events.
"""

import json
import os

from agent_calls import MODEL, get_client
from agents import LESSON_PLAN_SYSTEM_PROMPT
from json_utils import extract_json

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
