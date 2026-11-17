"""1.3 — the short quiz that decides a starting level when the student isn't
sure of it (or when their own estimate shouldn't just be taken on faith).

Generating the questions needs the model; GRADING them does not. Each
question is multiple choice with a known right answer and a difficulty, so
the level is computed by a plain rule: deterministic, free, and testable.
Asking a model to judge "which level does this student seem to be?" would be
slower, cost a call, and give a different answer on a re-run for the same
answers.

The correct answers are kept on the server. The questions go to the client
without them, and the answers come back to be graded here — so the student
can't be shown, or tamper with, what counts as correct.
"""

import json
import os
import uuid
from collections import OrderedDict

from agent_calls import MODEL, get_client
from agents import DIAGNOSTIC_SYSTEM_PROMPT
from json_utils import extract_json

DIAGNOSTIC_MODEL = os.environ.get("CLASSROOM_DIAGNOSTIC_MODEL", MODEL)
DIAGNOSTIC_MAX_TOKENS = 1200
DIAGNOSTIC_MAX_RETRIES = 2
QUESTION_COUNT = 4
DIFFICULTIES = ("basic", "intermediate", "advanced")

# In-memory, bounded: a diagnostic is short-lived (one sitting), and losing
# one to a restart just means the student sits it again.
_MAX_KEPT = 200
_DIAGNOSTICS: "OrderedDict[str, dict]" = OrderedDict()


class DiagnosticGenerationError(Exception):
    pass


class UnknownDiagnosticError(KeyError):
    pass


class InvalidAnswersError(ValueError):
    pass


def generate_diagnostic(topic: str, api_key: str | None = None) -> dict:
    """Returns {"id", "questions": [{"question", "options", "difficulty"}]} —
    with the right answers withheld."""
    last_error = None
    for _ in range(DIAGNOSTIC_MAX_RETRIES):
        response = get_client(api_key).messages.create(
            model=DIAGNOSTIC_MODEL,
            max_tokens=DIAGNOSTIC_MAX_TOKENS,
            system=DIAGNOSTIC_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"נושא: {topic}"}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
        try:
            questions = _validate(extract_json(raw))
            break
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError) as e:
            last_error = e
            print(f"[generate_diagnostic] malformed diagnostic JSON, retrying: {e}; raw={raw[:300]!r}")
    else:
        raise DiagnosticGenerationError(f"לא הצלחתי לבנות בוחן אבחון: {last_error}")

    diagnostic_id = str(uuid.uuid4())
    _DIAGNOSTICS[diagnostic_id] = {"topic": topic, "questions": questions}
    while len(_DIAGNOSTICS) > _MAX_KEPT:
        _DIAGNOSTICS.popitem(last=False)

    return {
        "id": diagnostic_id,
        "questions": [
            {"question": q["question"], "options": q["options"], "difficulty": q["difficulty"]}
            for q in questions
        ],
    }


def _validate(questions) -> list:
    if not isinstance(questions, list) or len(questions) < QUESTION_COUNT:
        raise ValueError(f"expected at least {QUESTION_COUNT} questions")
    questions = questions[:QUESTION_COUNT]
    for q in questions:
        if not (isinstance(q.get("question"), str) and q["question"].strip()):
            raise ValueError("question missing text")
        options = q.get("options")
        if not (isinstance(options, list) and len(options) >= 2):
            raise ValueError("question missing valid options")
        correct = q.get("correct_index")
        if isinstance(correct, bool) or not isinstance(correct, int) or not (0 <= correct < len(options)):
            raise ValueError("question has an invalid correct_index")
        if q.get("difficulty") not in DIFFICULTIES:
            raise ValueError("question has an unknown difficulty")
    # The rule below reads the questions in order of difficulty.
    order = {d: i for i, d in enumerate(DIFFICULTIES)}
    return sorted(questions, key=lambda q: order[q["difficulty"]])


def level_from_results(results: list) -> str:
    """results: [(difficulty, was_correct), ...]

    - Missing ANY basic question means the foundations aren't solid: beginner.
    - Everything right, advanced included: expert.
    - Otherwise: intermediate — the basics are there, the top isn't.

    Deliberately conservative about "expert": a lucky guess on four-option
    questions is plausible, so the top level needs a clean sweep. And the
    cost of being wrong is asymmetric — under-placing means a slightly
    slower start, over-placing means material explained too briefly to a
    student who needed it in full.
    """
    if any(not correct for difficulty, correct in results if difficulty == "basic"):
        return "beginner"
    if results and all(correct for _, correct in results):
        return "expert"
    return "intermediate"


def grade_diagnostic(diagnostic_id: str, answers: list) -> dict:
    entry = _DIAGNOSTICS.get(diagnostic_id)
    if entry is None:
        raise UnknownDiagnosticError(diagnostic_id)
    questions = entry["questions"]

    if not isinstance(answers, list) or len(answers) != len(questions):
        raise InvalidAnswersError(f"expected {len(questions)} answers")

    # Answers arrive in the order the questions were sent. An unanswered
    # question is sent as null and counts as wrong — the student not
    # knowing is exactly what the quiz is there to find out.
    results = []
    for q, answer in zip(questions, answers):
        if answer is not None and (isinstance(answer, bool) or not isinstance(answer, int)):
            raise InvalidAnswersError("each answer must be an option index or null")
        results.append((q["difficulty"], answer == q["correct_index"]))

    level = level_from_results(results)
    correct = sum(1 for _, ok in results if ok)
    # One use per diagnostic: re-grading the same questions with new answers
    # would let a student retry until they hit the level they wanted.
    _DIAGNOSTICS.pop(diagnostic_id, None)
    return {"level": level, "correct": correct, "total": len(results)}
