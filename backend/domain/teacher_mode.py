"""The teacher's explicit state machine.

Before this module existed, "what is the teacher doing right now" was
re-derived independently in four different places (orchestrator.py,
lesson_plan.py, main.py's _lesson_status) from combinations of booleans on
Session — awaiting_user, activity_teacher_explained, activity_index vs
len(activities). TeacherMode is now the one place that names every state the
teacher can be in, and ALLOWED_TRANSITIONS is the one place that says which
moves between them are legal. Lesson (lesson.py) is the only thing allowed
to call transition_to(); everything else just reads lesson.mode.

A normal activity's lifecycle:
    TEACHING -> DEMONSTRATING (pool-agent chatter, 0+ beats, self-loop)
             -> ASKING_CHECKPOINT (budget spent, question not yet sent)
             -> AWAITING_ANSWER (question sent, waiting on the real student)
             -> TRANSITIONING (answer showed understanding)
             -> TEACHING (next activity) | COMPLETED (no activities left)
    or, on a misunderstood answer:
             AWAITING_ANSWER -> RETEACHING -> DEMONSTRATING | ASKING_CHECKPOINT
ANSWERING_QUESTION is reachable from, and returns to, every other mode: an
aside question (from the student or a pool agent) can interrupt the flow at
any point without losing where the lesson was.
"""

from enum import Enum


class TeacherMode(Enum):
    TEACHING = "teaching"  # explaining an activity's material for the first time
    DEMONSTRATING = "demonstrating"  # autonomous pool-agent chatter about the material (budget not yet spent)
    ASKING_CHECKPOINT = "asking_checkpoint"  # budget spent; the checkpoint question itself hasn't been sent yet
    AWAITING_ANSWER = "awaiting_answer"  # checkpoint question sent, waiting on the real student
    ANSWERING_QUESTION = "answering_question"  # an aside question interrupted the flow above
    RETEACHING = "reteaching"  # the checkpoint answer showed misunderstanding; explaining again
    TRANSITIONING = "transitioning"  # answer showed understanding; about to move to the next activity
    COMPLETED = "completed"  # no activities left — terminal


class InvalidTransitionError(Exception):
    """Raised when something tries to move the teacher between two modes
    that don't have a legal path between them. Fails loudly instead of
    silently letting the lesson drift into an inconsistent state."""


_RESUMABLE = {
    TeacherMode.TEACHING, TeacherMode.DEMONSTRATING, TeacherMode.ASKING_CHECKPOINT,
    TeacherMode.AWAITING_ANSWER, TeacherMode.RETEACHING, TeacherMode.TRANSITIONING, TeacherMode.COMPLETED,
}

ALLOWED_TRANSITIONS: dict[TeacherMode, set[TeacherMode]] = {
    TeacherMode.TEACHING: {TeacherMode.DEMONSTRATING, TeacherMode.ASKING_CHECKPOINT, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.DEMONSTRATING: {TeacherMode.DEMONSTRATING, TeacherMode.ASKING_CHECKPOINT, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.ASKING_CHECKPOINT: {TeacherMode.AWAITING_ANSWER, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.AWAITING_ANSWER: {TeacherMode.TRANSITIONING, TeacherMode.RETEACHING, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.RETEACHING: {TeacherMode.DEMONSTRATING, TeacherMode.ASKING_CHECKPOINT, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.TRANSITIONING: {TeacherMode.TEACHING, TeacherMode.COMPLETED, TeacherMode.ANSWERING_QUESTION},
    TeacherMode.COMPLETED: {TeacherMode.ANSWERING_QUESTION},
    # ANSWERING_QUESTION can return to wherever it interrupted.
    TeacherMode.ANSWERING_QUESTION: _RESUMABLE | {TeacherMode.ANSWERING_QUESTION},
}


def can_transition(current: TeacherMode, target: TeacherMode) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
