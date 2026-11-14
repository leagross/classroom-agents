"""End-of-lesson flashcards for spaced repetition — same shape and retry
pattern as quiz.py, just a different output format."""

import json
import os

from agent_calls import MODEL, get_client
from agents import FLASHCARDS_SYSTEM_PROMPT
from json_utils import extract_json
from session_state import Session

FLASHCARDS_MODEL = os.environ.get("CLASSROOM_FLASHCARDS_MODEL", MODEL)
FLASHCARDS_MAX_TOKENS = 1200
FLASHCARDS_MAX_RETRIES = 2


class FlashcardsGenerationError(Exception):
    pass


def generate_flashcards(session: Session, api_key: str | None = None) -> list:
    user_content = session.full_transcript_text()
    last_error = None
    for _ in range(FLASHCARDS_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=FLASHCARDS_MODEL,
            max_tokens=FLASHCARDS_MAX_TOKENS,
            system=FLASHCARDS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            cards = extract_json(raw)
            if not isinstance(cards, list) or not cards:
                raise ValueError("expected a non-empty JSON array")
            for card in cards:
                if not (isinstance(card.get("front"), str) and card["front"]):
                    raise ValueError("card missing front")
                if not (isinstance(card.get("back"), str) and card["back"]):
                    raise ValueError("card missing back")
            return cards
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            last_error = e
            print(f"[generate_flashcards] malformed flashcards JSON, retrying: {e}; raw={raw[:300]!r}")

    raise FlashcardsGenerationError(f"לא הצלחתי לבנות כרטיסיות תקינות: {last_error}")
