"""The one place that moves a session's state to and from the database.

Before this existed, every site that mutated a session also called the
matching db.update_* itself, inline, mid-function — so adding a field meant
touching the dataclass, the schema, and every mutation site, and a mutation
whose save call was forgotten silently stopped persisting. Now the
orchestrator calls save() once per turn (in a finally, so a client
disconnect mid-stream still persists what already happened) and nothing
else writes lesson state.

The database is optional (db.py no-ops without DATABASE_URL), so every
method here works unchanged with persistence switched off.
"""

from domain.lesson import Lesson
from domain.teacher_mode import TeacherMode


def _mode_from_legacy_row(row: dict, lesson_complete: bool) -> TeacherMode:
    """A lessons row written before the teacher_mode column existed. The old
    booleans can't tell "about to teach" from "re-teaching" from
    "mid-chatter", so pick the safe reading: if it was waiting on the
    student, it was waiting; otherwise start the current activity over by
    teaching it. Re-teaching costs the student a repeat; guessing
    AWAITING_ANSWER wrongly would wedge the lesson waiting for an answer to
    a question nobody asked."""
    if lesson_complete:
        return TeacherMode.COMPLETED
    if row.get("awaiting_user"):
        return TeacherMode.AWAITING_ANSWER
    return TeacherMode.TEACHING


def lesson_from_row(row: dict) -> Lesson:
    """Rebuild the Lesson state machine from a persisted lessons row."""
    plan = row.get("plan")
    activity_index = row.get("activity_index") or 0
    # Lesson.__post_init__ forces COMPLETED for a plan-less or exhausted
    # lesson regardless of what was stored, so compute that the same way here.
    activities = (plan or {}).get("activities", [])
    complete = plan is None or activity_index >= len(activities)

    stored = row.get("teacher_mode")
    if stored:
        try:
            mode = TeacherMode(stored)
        except ValueError:
            mode = _mode_from_legacy_row(row, complete)
    else:
        mode = _mode_from_legacy_row(row, complete)

    stored_resume = row.get("resume_mode")
    resume_mode = None
    if stored_resume:
        try:
            resume_mode = TeacherMode(stored_resume)
        except ValueError:
            resume_mode = None

    # A row saved mid-aside-question needs both halves to come back, or
    # finish_answering_question() would raise on the next turn.
    if mode is TeacherMode.ANSWERING_QUESTION and resume_mode is None:
        mode = _mode_from_legacy_row(row, complete)

    return Lesson(
        plan=plan,
        activity_index=activity_index,
        mode=mode,
        autonomous_turns_used=row.get("autonomous_turns_used") or 0,
        homework_delivered=bool(row.get("homework_delivered")),
        resume_mode=resume_mode,
    )


class SessionRepository:
    """Thin seam over db.py. Takes the db module as a dependency so tests
    can pass a stub instead of reaching for a real Postgres."""

    def __init__(self, db_module=None):
        if db_module is None:
            import db as db_module
        self._db = db_module

    def save(self, session):
        """Persist everything mutable about a session: the conversation
        counters and the lesson state machine. Idempotent — safe to call
        more than once per turn, and safe to call on a plan-less session."""
        self._db.update_lesson_state(
            session.id, session.round_count, session.pool_turn_index, session.next_jester_round
        )
        lesson = session.lesson
        self._db.update_lesson_plan_state(
            session.id,
            lesson.activity_index,
            lesson.autonomous_turns_used,
            lesson.autoplay_paused,
            teacher_mode=lesson.mode.value,
            resume_mode=lesson.resume_mode.value if lesson.resume_mode else None,
            homework_delivered=lesson.homework_delivered,
        )

    def add_message(self, session_id: str, msg):
        self._db.insert_message(session_id, msg.agent_key, msg.display_name, msg.color, msg.content)

    def load_row(self, session_id: str):
        return self._db.load_lesson(session_id)

    def load_messages(self, session_id: str):
        return self._db.load_messages(session_id)
