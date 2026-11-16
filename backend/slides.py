"""Slides for the board.

A deck is built per ACTIVITY, not per lesson, and only when that activity
is actually reached — the same laziness as lesson plans within a syllabus.
Generating slides for all five activities up front would spend five model
calls on a lesson the student may leave after the first one.

On external design tools: the slide CONTENT is produced here, and that is
what the board renders today. Turning that content into designed slides via
Canva (or pulling a deck out of NotebookLM) is a separate provider step —
see SlideProvider below for where it attaches. Neither is wired up: Canva's
Connect API needs a reviewed app, and NotebookLM has no public API at all,
so nothing here pretends to call them.
"""

import json
import os

from agent_calls import MODEL, get_client
from agents import SLIDES_SYSTEM_PROMPT
from json_utils import extract_json

SLIDES_MODEL = os.environ.get("CLASSROOM_SLIDES_MODEL", MODEL)
SLIDES_MAX_TOKENS = 1200
SLIDES_MAX_RETRIES = 2


class SlideGenerationError(Exception):
    pass


def generate_activity_slides(topic: str, activity: dict, api_key: str | None = None) -> list:
    """Returns [{"title", "bullets": [...]}] for one activity."""
    user_content = (
        f"נושא השיעור: {topic}\n"
        f"הפעילות שהמורה עומד ללמד: {activity.get('title', '')}\n"
        f"תיאור הפעילות: {activity.get('summary', '')}"
    )
    last_error = None
    for _ in range(SLIDES_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=SLIDES_MODEL,
            max_tokens=SLIDES_MAX_TOKENS,
            system=SLIDES_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            slides = extract_json(raw)
            if not isinstance(slides, list) or not slides:
                raise ValueError("expected a non-empty JSON array")
            for slide in slides:
                if not (isinstance(slide.get("title"), str) and slide["title"]):
                    raise ValueError("slide missing title")
                bullets = slide.get("bullets")
                if not isinstance(bullets, list):
                    slide["bullets"] = []
                else:
                    slide["bullets"] = [str(b) for b in bullets if str(b).strip()]
            return slides
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError) as e:
            last_error = e
            print(f"[generate_activity_slides] malformed slides JSON, retrying: {e}; raw={raw[:300]!r}")

    raise SlideGenerationError(f"לא הצלחתי לבנות מצגת לשלב הזה: {last_error}")


class SlideProvider:
    """Where a real design tool would attach.

    render(slides, topic) takes the generated content and returns the same
    list, optionally with an "image_url" on each slide pointing at a
    rendered design. The default provider adds nothing, so the board falls
    back to rendering the text itself — which is also exactly what happens
    if a configured provider fails, so a design outage can never cost the
    lesson its slides.
    """

    name = "text"

    def render(self, slides: list, topic: str) -> list:
        return slides


_provider = SlideProvider()


def set_provider(provider: SlideProvider):
    """Swap in a Canva-backed provider once credentials exist."""
    global _provider
    _provider = provider


def build_slides(topic: str, activity: dict, api_key: str | None = None) -> list:
    slides = generate_activity_slides(topic, activity, api_key=api_key)
    try:
        return _provider.render(slides, topic)
    except Exception as e:  # noqa: BLE001 — a design tool outage must not lose the slides
        print(f"[build_slides] provider {_provider.name} failed, serving text slides: {e!r}")
        return slides
