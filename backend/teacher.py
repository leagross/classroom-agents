"""Fact-checking the teacher's answers before a student ever sees them —
the one guarantee the whole classroom is built around: the teacher is
always right, even though the model that plays the teacher can hallucinate.
"""

import os

from agent_calls import call_agent, get_client
from agents import TEACHER, VERIFIER_SYSTEM_PROMPT
from session_state import Session

VERIFIER_MODEL = os.environ.get("CLASSROOM_VERIFIER_MODEL", "claude-haiku-5-5")
VERIFIER_MAX_TOKENS = 300
MAX_VERIFY_RETRIES = 2


def verify_teacher_answer(topic: str, answer: str, api_key: str | None = None) -> tuple[bool, str]:
    verify_prompt = f"נושא: {topic}\n\nתשובת המורה:\n{answer}"
    response = get_client(api_key).messages.create(
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


def get_validated_teacher_reply(session: Session, api_key: str | None = None, image: dict | None = None) -> str:
    transcript = session.transcript_text()
    answer = call_agent(TEACHER, transcript, api_key=api_key, image=image)
    for _ in range(MAX_VERIFY_RETRIES):
        ok, reason = verify_teacher_answer(session.topic, answer, api_key=api_key)
        if ok:
            return answer
        answer = call_agent(
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
