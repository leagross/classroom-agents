"""The teacher's explicit state machine.

Before this module existed, "what is the teacher doing right now" was
re-derived independently in four different places (orchestrator.py,
lesson_plan.py, main.py's _lesson_status) from combinations of booleans on
Session — awaiting_user, activity_teacher_explained, activity_index vs
len(activities). Those four derivations were a real source of bugs (the
non-streaming /api/message route never implemented checkpoint logic at all,
because it never re-derived "are we answering a checkpoint" the way the
streaming route did).

TeacherMode is now the one place that names every state the teacher can be
in, and ALLOWED_TRANSITIONS is the one place that says which moves between
them are legal. Lesson (lesson.py) is the only thing allowed to call
transition_to(); everything else just reads lesson.current_mode.
"""

from enum import Enum


class TeacherMode(Enum):
    TEACHING = "teaching"  # explaining an activity's material for the first time
    DEMONSTRATING = "demonstrating"  # showing a worked example tied to that material
    AWAITING_ANSWER = "awaiting_answer"  # checkpoint question asked, waiting on the real student
    ANSWERING_QUESTION = "answering_question"  # reacting to a student/pool-agent question
    RETEACHING = "reteaching"  # the checkpoint answer showed misunderstanding; explaining again
    TRANSITIONING = "transitioning"  # current activity is done, moving to the next one


class InvalidTransitionError(Exception):
    """Raised when something tries to move the teacher between two modes
    that don't have a legal path between them — e.g. jumping straight from
    TEACHING to AWAITING_ANSWER without ever demonstrating or exhausting the
    activity's autonomous budget. Fails loudly instead of silently letting
    the lesson drift into an inconsistent state."""


# Each mode's value is the set of modes it may move to next. TRANSITIONING
# can reach TEACHING because that's exactly what starting the next activity
# looks like; it's also its own valid starting point (the very first
# activity of a lesson begins "transitioning in").
ALLOWED_TRANSITIONS: dict[TeacherMode, set[TeacherMode]] = {
    TeacherMode.TEACHING: {TeacherMode.DEMONSTRATING, TeacherMode.AWAITING_ANSWER, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.DEMONSTRATING: {TeacherMode.AWAITING_ANSWER, TeacherMode.ANSWERING_QUESTION, TeacherMode.DEMONSTRATING},
    TeacherMode.AWAITING_ANSWER: {TeacherMode.RETEACHING, TeacherMode.TRANSITIONING, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.ANSWERING_QUESTION: {TeacherMode.TEACHING, TeacherMode.DEMONSTRATING, TeacherMode.AWAITING_ANSWER, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.RETEACHING: {TeacherMode.DEMONSTRATING, TeacherMode.AWAITING_ANSWER},
    TeacherMode.TRANSITIONING: {TeacherMode.TEACHING},
}


def can_transition(current: TeacherMode, target: TeacherMode) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
