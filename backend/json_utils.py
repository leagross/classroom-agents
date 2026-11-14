"""Shared helper for parsing structured JSON out of a model response.

Used by both quiz.py (JSON array) and lesson_plan.py (JSON object) — the
model is instructed to return raw JSON in both cases, so the extraction
rules are identical and belong in exactly one place.
"""

import json


def extract_json(raw: str):
    """Models occasionally wrap raw JSON in a ```json code fence anyway —
    strip that defensively before parsing instead of failing over a
    formatting slip."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
