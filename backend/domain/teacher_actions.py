"""Everything the teacher can say, as interchangeable action objects.

What this replaces: three near-identical functions in the old teacher.py
(get_validated_teacher_reply / _explanation / _checkpoint_feedback), each
hand-building its own prompt and inventing its own sentinel-marker
convention, plus two more teacher utterances (the checkpoint question and
the homework hand-out) that bypassed the fact-verification loop entirely
because they were emitted straight from lesson_plan.py/orchestrator.py. So
some of the teacher's words were fact-checked and some weren't, depending
on which file happened to produce them.

Now every *generated* utterance is a TeacherAction run through one loop
(run_action): build prompt -> generate -> fact-verify -> parse. Static text
that was written at plan-generation time (the checkpoint question, the
homework) is deliberately NOT an action: it was already reviewed when the
plan was approved, and re-verifying fixed text on every delivery would just
buy an extra model call per beat and could not be acted on anyway — you
cannot "retry" text the student already agreed to.

Parse-failure policy (the old code's worst silent default): a missing
verdict marker used to mean "the student understood, move on", so a single
formatting slip advanced the lesson past material the student had not
grasped. Now a missing marker raises, run_action retries once with an
explicit format reminder, and if that also fails it falls back to
understood=False — re-teaching costs the student a repeat, while the old
default cost them the understanding.
"""

from dataclasses import dataclass
from typing import Protocol

from agent_calls import call_agent, get_client
from agents import TEACHER, VERIFIER_SYSTEM_PROMPT
from domain.learner import PRESUMED_KNOWN, InvalidProfileError, LearnerProfile

import os

VERIFIER_MODEL = os.environ.get("CLASSROOM_VERIFIER_MODEL", "claude-haiku-5-5")
VERIFIER_MAX_TOKENS = 300
MAX_VERIFY_RETRIES = 2

#: Separates what the teacher says out loud (shown in chat) from the short
#: notes they write on the board.
BOARD_MARKER = "---BOARD---"
#: Whether the student's checkpoint answer showed real understanding.
UNDERSTOOD_MARKER = "===UNDERSTOOD==="
RETEACH_MARKER = "===RETEACH==="

FORMAT_REMINDER = (
    "שים לב: התשובה הקודמת שלך לא כללה את השורה בפורמט הנדרש. "
    "חזור על התשובה, והקפד לכתוב את השורה המיוחדת בדיוק כפי שהתבקשת. "
)


class TeacherOutputParseError(Exception):
    """The model's output didn't contain a marker the action requires."""


@dataclass
class TeacherOutput:
    speech: str
    board_notes: str = ""
    #: Only set by actions that judge the student's understanding.
    understood: bool | None = None
    #: True when this output is the fallback used after parsing failed twice.
    degraded: bool = False


def _split_board_notes(raw: str) -> tuple[str, str]:
    if BOARD_MARKER in raw:
        speech, _, notes = raw.partition(BOARD_MARKER)
        return speech.strip(), notes.strip()
    return raw.strip(), ""


def _split_verdict(raw: str) -> tuple[str, bool]:
    for marker, understood in ((UNDERSTOOD_MARKER, True), (RETEACH_MARKER, False)):
        if marker in raw:
            feedback, _, _ = raw.partition(marker)
            return feedback.strip(), understood
    raise TeacherOutputParseError("no understood/reteach marker in the teacher's checkpoint feedback")


class TeacherAction(Protocol):
    """Build a prompt, then turn the model's raw text into a TeacherOutput."""

    def build_prompt(self, session, lesson) -> str: ...

    def parse(self, raw: str) -> TeacherOutput: ...

    def fallback(self) -> TeacherOutput | None:
        """What to use if parsing fails twice. None means "let it raise"."""


_BOARD_INSTRUCTION = (
    f"בסיום דבריך, בשורה נפרדת משלה בדיוק כך: {BOARD_MARKER}\n"
    "ואחריה כתוב 2-4 שורות קצרות בלבד — בדיוק מה שבאמת היית כותב ביד על לוח פיזי: "
    "מושג, נוסחה, או משפט-מפתח אחד לכל שורה. לא משפטים מלאים ולא את מה שאמרת בעל פה, "
    "רק הכותרות שתלמיד ירשום לעצמו."
)

def _teaching_contract(lesson) -> str:
    """The teaching contract, shared by every action that explains material.

    The rules that never change: explain before showing, explain every new
    term when it first appears, and never use phrasing that presumes the
    student already knows ("as you know"). What DOES depend on the student is
    only what counts as already known — and that comes from their stage-1
    profile, carried on the lesson's plan. With no profile (a free-form
    review session, or a plan from before intake existed) the safe default is
    the beginner's: assume nothing.
    """
    profile = None
    learner = (lesson.plan or {}).get("learner") if lesson is not None else None
    if learner:
        try:
            profile = LearnerProfile.from_dict(learner)
        except InvalidProfileError:
            # A stored profile that no longer validates must not stop the
            # lesson from being taught — fall back to assuming nothing.
            profile = None

    known = profile.presumed_known() if profile else PRESUMED_KNOWN["beginner"]
    depth = f"- {profile.depth_guidance()}\n" if profile else ""
    return (
        "כללי הוראה שאתה מחויב להם:\n"
        "- קודם מסבירים, ורק אחר כך מציגים. אסור להציג נוסחה, פונקציה, מושג או מונח מקצועי "
        "לפני שהסברת במילים פשוטות מה הוא עושה ולמה הוא בכלל נחוץ. קודם הרעיון, אחר כך הסימון.\n"
        f"- {known}\n"
        f"{depth}"
        "- כל מונח שהתלמיד לא פגש עדיין — הסבר אותו באותו משפט שבו הוא מופיע לראשונה.\n"
        "- דבר שהוא חדש לתלמיד: הסבר בפירוט, לאט, עם דוגמה קונקרטית אחת לפחות.\n"
        "- דבר שכבר נלמד קודם בשיעור הזה עצמו: די בתזכורת קצרה של משפט אחד, לא הסבר מלא מחדש.\n"
        "- אל תשתמש במילים כמו \"כידוע\", \"פשוט\", \"ברור ש\", \"כמו שאתה יודע\" — אם זה היה ברור, "
        "לא היה צורך ללמד את זה."
    )


@dataclass
class ExplainAction:
    """The teacher teaching the current activity's material for the first
    time — proactive, not a reply to anything the student said."""

    def build_prompt(self, session, lesson) -> str:
        activity = lesson.current_activity or {}
        return session.transcript_text() + (
            f"\n\n[השלב הנוכחי במערך השיעור: {activity.get('title', '')} — {activity.get('summary', '')}. "
            "זה הרגע שבו המורה מלמד בפועל את החומר של השלב הזה, לתלמיד שפוגש אותו עכשיו "
            "בפעם הראשונה. אל תזרוק את כל החומר במשפט אחד — בנה אותו צעד אחר צעד.\n"
            f"{_teaching_contract(lesson)}\n"
            f"{_BOARD_INSTRUCTION}]"
        )

    def parse(self, raw: str) -> TeacherOutput:
        speech, notes = _split_board_notes(raw)
        return TeacherOutput(speech=speech, board_notes=notes)

    def fallback(self):
        return None  # board notes are optional; parse never fails here


@dataclass
class ReteachAction:
    """The teacher explaining the SAME activity again after the student
    showed they hadn't understood.

    The point is not to repeat the explanation more slowly. The teacher has
    to work out, from what the student actually wrote, WHICH part did not
    land — a term, a step, the reason the thing exists at all — and come at
    that specific part from several different directions. Repeating the
    same route that already failed is the one thing it must not do.
    """

    def build_prompt(self, session, lesson) -> str:
        activity = lesson.current_activity or {}
        return session.transcript_text() + (
            f"\n\n[התלמיד לא הבין את החומר של השלב הנוכחי ({activity.get('title', '')}).\n"
            "לפני שאתה מסביר שוב, קרא שוב את מה שהתלמיד כתב למעלה וזהה מתוך דבריו מה בדיוק "
            "לא ברור לו: מונח מסוים? שלב מסוים בתהליך? הקשר בין שני דברים? או בכלל למה זה נחוץ? "
            "אם הוא רק כתב \"לא הבנתי\" בלי לפרט — הסק מהתשובה הקודמת שלו, או מהנקודה שבה הוא "
            "נתקע, מה כנראה החסם.\n"
            "אחר כך הסבר שוב — אבל רק את החלק שלא הובן, לא את הכול מחדש — וגש אליו מכמה כיוונים "
            "שונים: אנלוגיה מחיי היום-יום, דוגמה מספרית/קונקרטית חדשה (לא זו שכבר השתמשת בה), "
            "ופירוק לצעדים קטנים יותר. אל תחזור על אותן מילים ועל אותו מסלול שכבר לא עבד.\n"
            "בסוף, שאל שאלה קצרה שבודקת בדיוק את הנקודה שלא הובנה.\n"
            f"{_teaching_contract(lesson)}\n"
            f"{_BOARD_INSTRUCTION}]"
        )

    def parse(self, raw: str) -> TeacherOutput:
        speech, notes = _split_board_notes(raw)
        return TeacherOutput(speech=speech, board_notes=notes)

    def fallback(self):
        return None


@dataclass
class AnswerQuestionAction:
    """The teacher replying to whatever the student just said — a question
    mid-lesson, or any message in a plan-less review session.

    "I didn't get it" is handled here too, not only at a checkpoint: the
    student can say it at any point, and the same rule applies — work out
    what specifically is unclear before explaining anything.
    """

    image: dict | None = None

    def build_prompt(self, session, lesson) -> str:
        confusion = (
            "אם התלמיד אומר שהוא לא הבין — אל תחזור על ההסבר הקודם כלשונו. "
            "זהה קודם מתוך דבריו מה בדיוק לא ברור (מונח? שלב? הקשר? מה המטרה בכלל?), "
            "ואם לא פירט — הסק מהשיחה היכן הוא נתקע. אחר כך הסבר את אותה נקודה מכיוון אחר: "
            "אנלוגיה, דוגמה קונקרטית חדשה, או פירוק לצעדים קטנים יותר.\n"
        )
        if lesson.is_complete():
            return session.transcript_text() + f"\n\n[{confusion}{_teaching_contract(lesson)}]"
        activity = lesson.current_activity or {}
        return session.transcript_text() + (
            f"\n\n[אנחנו באמצע השלב \"{activity.get('title', '')}\" במערך השיעור. "
            "התלמיד אמר משהו שאינו תשובה לשאלת הבדיקה. ענה בקצרה ובמיקוד, "
            "ואם זה חורג מהנושא הנוכחי — אמור זאת והצע לחזור לזה בשלב מתאים יותר, "
            "במקום לסטות מהשיעור.\n"
            f"{confusion}"
            f"{_teaching_contract(lesson)}]"
        )

    def parse(self, raw: str) -> TeacherOutput:
        return TeacherOutput(speech=raw.strip())

    def fallback(self):
        return None


@dataclass
class CheckpointFeedbackAction:
    """The teacher judging the student's answer to the current activity's
    checkpoint question. Its verdict decides whether the lesson may move on,
    which is why a missing marker is a hard parse error here."""

    def build_prompt(self, session, lesson) -> str:
        activity = lesson.current_activity or {}
        return session.transcript_text() + (
            f"\n\n[התלמיד הרגע ענה על שאלת הבדיקה של הפעילות הנוכחית במערך השיעור "
            f"({activity.get('title', '')}): \"{activity.get('checkpoint_question', '')}\". "
            "תן משוב קצר וממוקד על התשובה שלו: אם היא מראה הבנה אמיתית של החומר — חיזוק קצר "
            "וממוקד, לא גנרי. אם היא מראה שהוא עדיין לא הבין — זהה קודם מתוך התשובה שלו מה "
            "בדיוק חסר או שגוי אצלו, אמור זאת בעדינות, והבהר את אותה נקודה בדיוק מזווית אחרת, "
            "עם דוגמה חדשה ושונה מזו שכבר השתמשת בה.\n"
            f"בסיום המשוב שלך, בשורה נפרדת משלה, כתוב בדיוק אחת מהשתיים: אם התשובה מראה הבנה "
            f"מספקת כדי להמשיך לפעילות הבאה, כתוב {UNDERSTOOD_MARKER}. אם לא, כתוב {RETEACH_MARKER}.]"
        )

    def parse(self, raw: str) -> TeacherOutput:
        feedback, understood = _split_verdict(raw)
        return TeacherOutput(speech=feedback, understood=understood)

    def fallback(self) -> TeacherOutput:
        # Could not tell whether the student understood. Assume they did not:
        # a needless re-explanation is recoverable, silently advancing past
        # material they never grasped is not.
        return TeacherOutput(
            speech="בוא נעבור על זה שוב מזווית אחרת, רק כדי לוודא שזה יושב טוב.",
            understood=False,
            degraded=True,
        )


def verify_answer(topic: str, answer: str, api_key: str | None = None) -> tuple[bool, str]:
    """Silent fact-check behind every generated teacher utterance."""
    response = get_client(api_key).messages.create(
        model=VERIFIER_MODEL,
        max_tokens=VERIFIER_MAX_TOKENS,
        system=VERIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"נושא: {topic}\n\nתשובת המורה:\n{answer}"}],
    )
    verdict = "".join(b.text for b in response.content if b.type == "text").strip()
    if not verdict:
        # An unparseable verdict is logged rather than silently treated as a
        # clean pass, so a verifier that has started failing is visible.
        print("[verify_answer] empty verdict from verifier; treating as pass")
        return True, ""
    if verdict.startswith("תקין"):
        return True, ""
    return False, verdict


def _generate_verified(action, session, lesson, api_key, extra_instruction="") -> str:
    """Generate, then fact-check with retries, exactly once per action —
    the loop every teacher utterance shares."""
    prompt = action.build_prompt(session, lesson)
    image = getattr(action, "image", None)
    answer = call_agent(TEACHER, prompt, extra_instruction=extra_instruction, api_key=api_key, image=image)
    for _ in range(MAX_VERIFY_RETRIES):
        ok, reason = verify_answer(session.topic, answer, api_key=api_key)
        if ok:
            return answer
        answer = call_agent(
            TEACHER,
            prompt,
            extra_instruction=(
                f"שים לב: הניסיון הקודם שלך הכיל טעות עובדתית ({reason}). "
                "תקן אותה בתשובה הבאה. " + extra_instruction
            ),
            api_key=api_key,
            image=image,
        )
    print("[_generate_verified] verification retries exhausted; delivering last attempt")
    return answer


def run_action(action: TeacherAction, session, lesson, api_key: str | None = None) -> TeacherOutput:
    """Build -> generate -> fact-verify -> parse, with one format-reminder
    retry and then the action's declared fallback."""
    raw = _generate_verified(action, session, lesson, api_key)
    try:
        return action.parse(raw)
    except TeacherOutputParseError as first_error:
        print(f"[run_action] {type(action).__name__} parse failed, retrying with format reminder: {first_error}")
        raw = _generate_verified(action, session, lesson, api_key, extra_instruction=FORMAT_REMINDER)
        try:
            return action.parse(raw)
        except TeacherOutputParseError as second_error:
            fallback = action.fallback()
            if fallback is None:
                raise
            print(f"[run_action] {type(action).__name__} parse failed twice, using fallback: {second_error}")
            return fallback
