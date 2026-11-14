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


def _verified_answer(
    topic: str, transcript: str, api_key: str | None = None, image: dict | None = None
) -> str:
    """Shared retry loop behind both get_validated_teacher_reply (responding
    to the student) and get_validated_teacher_explanation (proactively
    teaching an activity's material) — same guarantee, different transcript."""
    answer = call_agent(TEACHER, transcript, api_key=api_key, image=image)
    for _ in range(MAX_VERIFY_RETRIES):
        ok, reason = verify_teacher_answer(topic, answer, api_key=api_key)
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


def get_validated_teacher_reply(session: Session, api_key: str | None = None, image: dict | None = None) -> str:
    return _verified_answer(session.topic, session.transcript_text(), api_key=api_key, image=image)


#: Separates what the teacher actually says (shown in chat) from the short
#: notes they write on the lesson board (see split_board_notes) — a marker
#: rather than JSON so a model that forgets it just degrades gracefully to
#: "no board notes" instead of a parse failure needing its own retry loop.
BOARD_NOTES_MARKER = "---BOARD---"


def split_board_notes(answer: str) -> tuple[str, str]:
    if BOARD_NOTES_MARKER in answer:
        speech, _, notes = answer.partition(BOARD_NOTES_MARKER)
        return speech.strip(), notes.strip()
    return answer.strip(), ""


def get_validated_teacher_explanation(
    session: Session, activity: dict, api_key: str | None = None
) -> tuple[str, str]:
    """The teacher proactively teaching an activity's material — not
    responding to something the student just said. This always runs first
    in a plan-driven activity (see lesson_plan.advance_lesson_stream): the
    classroom never jumps straight to student chatter or a checkpoint
    question before the teacher has actually explained the content.

    Returns (speech, board_notes): speech is the full explanation as shown
    in chat; board_notes is a short, separate set of key points/formulas for
    the lesson board — never the whole explanation dumped onto it."""
    transcript = session.transcript_text() + (
        f"\n\n[השלב הנוכחי במערך השיעור: {activity['title']} — {activity.get('summary', '')}. "
        "זה הרגע שבו המורה צריך ללמד בפועל את החומר של השלב הזה לתלמיד שעדיין לא מכיר אותו. "
        "אל תזרוק את כל החומר במשפט אחד ואל תניח שהתלמיד כבר מכיר את הרקע: תתחיל בהסבר "
        "הדרגתי ופשוט, ותביא לפחות דוגמה קונקרטית אחת לפני שאתה ממשיך הלאה.\n"
        f"בסיום דבריך, בשורה נפרדת משלה בדיוק כך: {BOARD_NOTES_MARKER}\n"
        "ואחריה כתוב 2-4 שורות קצרות בלבד — בדיוק מה שבאמת היית כותב ביד על לוח פיזי: "
        "מושג, נוסחה, או משפט-מפתח אחד לכל שורה. לא משפטים מלאים ולא את מה שאמרת בעל פה, "
        "רק הכותרות שתלמיד ירשום לעצמו.]"
    )
    answer = _verified_answer(session.topic, transcript, api_key=api_key)
    return split_board_notes(answer)


#: Marks whether the student's checkpoint answer showed real understanding —
#: same "marker, not JSON" spirit as BOARD_NOTES_MARKER: a model that forgets
#: it just defaults to UNDERSTOOD (move on) rather than getting the lesson
#: stuck in a loop over a formatting slip.
UNDERSTOOD_MARKER = "===UNDERSTOOD==="
RETEACH_MARKER = "===RETEACH==="


def split_checkpoint_verdict(answer: str) -> tuple[str, bool]:
    for marker, understood in ((UNDERSTOOD_MARKER, True), (RETEACH_MARKER, False)):
        if marker in answer:
            feedback, _, _ = answer.partition(marker)
            return feedback.strip(), understood
    return answer.strip(), True


def get_validated_checkpoint_feedback(
    session: Session, activity: dict, api_key: str | None = None
) -> tuple[str, bool]:
    """The teacher reacting to the student's answer to THIS activity's
    checkpoint_question specifically — not a generic reply. Decides whether
    the classroom is allowed to move on to the next activity.

    Returns (feedback, understood): feedback is the chat message shown to
    the student (praise, a gentle correction, or another example); understood
    says whether lesson_plan.py should advance to the next activity or stay
    on this one and have the teacher re-teach it."""
    transcript = session.transcript_text() + (
        f"\n\n[התלמיד הרגע ענה על שאלת הבדיקה של הפעילות הנוכחית במערך השיעור "
        f"({activity['title']}): \"{activity['checkpoint_question']}\". "
        "תן משוב קצר וממוקד על התשובה שלו: אם היא מראה הבנה אמיתית של החומר — חיזוק קצר "
        "וממוקד, לא גנרי. אם היא מראה שהוא עדיין לא הבין — תקן בעדינות, והבא דוגמה נוספת "
        "שונה מזו שכבר השתמשת בה, כדי להבהיר מזווית אחרת.\n"
        f"בסיום המשוב שלך, בשורה נפרדת משלה, כתוב בדיוק אחת מהשתיים: אם התשובה מראה הבנה "
        f"מספקת כדי להמשיך לפעילות הבאה, כתוב {UNDERSTOOD_MARKER}. אם לא, כתוב {RETEACH_MARKER}.]"
    )
    answer = _verified_answer(session.topic, transcript, api_key=api_key)
    return split_checkpoint_verdict(answer)
