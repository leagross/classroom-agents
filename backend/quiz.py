"""End-of-lesson quiz generation."""

import json
import os

from agent_calls import MODEL, get_client
from agents import QUIZ_SYSTEM_PROMPT
from json_utils import extract_json
from session_state import Session

QUIZ_MODEL = os.environ.get("CLASSROOM_QUIZ_MODEL", MODEL)
QUIZ_MAX_TOKENS = 1500
QUIZ_MAX_RETRIES = 2


class QuizGenerationError(Exception):
    pass


def generate_quiz(session: Session, api_key: str | None = None) -> list:
    user_content = session.full_transcript_text()
    last_error = None
    for _ in range(QUIZ_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=QUIZ_MODEL,
            max_tokens=QUIZ_MAX_TOKENS,
            system=QUIZ_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            questions = extract_json(raw)
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
