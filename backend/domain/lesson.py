"""Lesson: the single owner of "where is this plan-driven lesson right now."

Before this class existed, that question was answered independently in at
least four places (orchestrator.py's answering_checkpoint, lesson_plan.py's
advance_lesson_stream dispatch, main.py's _lesson_status, and implicitly
wherever activity_index was compared to len(activities)) by combining raw
booleans on Session. Those four derivations could — and did — drift apart:
the non-streaming /api/message route never implemented checkpoint logic at
all, because it never re-derived "are we answering a checkpoint" the way
the streaming route did.

Lesson wraps a session's plan and owns every read and every transition.
Everything else (the orchestrator, the routes) asks a Lesson instance, never
rebuilds the logic from raw fields.
"""

from dataclasses import dataclass, field

from domain.teacher_mode import InvalidTransitionError, TeacherMode, can_transition

DEFAULT_AUTONOMOUS_EXCHANGES = 1


@dataclass
class Lesson:
    plan: dict | None = None
    activity_index: int = 0
    mode: TeacherMode = TeacherMode.TEACHING
    autonomous_turns_used: int = 0
    homework_delivered: bool = False

    @property
    def activities(self) -> list:
        return (self.plan or {}).get("activities", [])

    @property
    def current_activity(self) -> dict | None:
        activities = self.activities
        if 0 <= self.activity_index < len(activities):
            return activities[self.activity_index]
        return None

    def is_complete(self) -> bool:
        """True once there is no plan at all, or the plan's activities are
        exhausted. The one place every other module should check instead of
        comparing activity_index to len(activities) itself."""
        return self.plan is None or self.current_activity is None

    @property
    def awaiting_user(self) -> bool:
        """True exactly when the student's next message should be treated as
        an answer to the current activity's checkpoint question, rather than
        a generic chat message. Once the lesson is complete, there is no
        more checkpoint to answer — ordinary chat resumes."""
        if self.is_complete():
            return True
        return self.mode is TeacherMode.AWAITING_ANSWER

    def transition_to(self, target: TeacherMode):
        if not can_transition(self.mode, target):
            raise InvalidTransitionError(f"{self.mode} -> {target} is not a legal teacher-mode transition")
        self.mode = target

    def budget(self) -> int:
        activity = self.current_activity
        if not activity:
            return 0
        return activity.get("autonomous_exchanges", DEFAULT_AUTONOMOUS_EXCHANGES)

    def budget_spent(self) -> bool:
        return self.autonomous_turns_used >= self.budget()

    def finish_explaining(self):
        """Called once the teacher has just taught the current activity's
        material for the first time (mode was TEACHING). Moves straight to
        waiting for the checkpoint if the activity has no autonomous budget,
        otherwise opens the pool-agent chatter phase."""
        self.transition_to(TeacherMode.AWAITING_ANSWER if self.budget() == 0 else TeacherMode.DEMONSTRATING)

    def record_autonomous_turn(self):
        """One pool-agent 'beat' during the DEMONSTRATING phase has happened.
        Moves on to waiting for the checkpoint once the budget is spent;
        otherwise stays in DEMONSTRATING (a legal self-loop)."""
        self.autonomous_turns_used += 1
        if self.budget_spent():
            self.transition_to(TeacherMode.AWAITING_ANSWER)

    def record_checkpoint_result(self, understood: bool):
        """Called once a real student has answered the current activity's
        checkpoint question. understood=True readies the lesson to move to
        the next activity (advance_to_next_activity); understood=False stays
        on this activity and has the teacher re-teach it."""
        if understood:
            self.transition_to(TeacherMode.TRANSITIONING)
        else:
            self.transition_to(TeacherMode.RETEACHING)
            self.autonomous_turns_used = 0

    def retry_current_activity(self):
        """Called once the teacher has re-taught the activity after a
        misunderstood checkpoint (mode was RETEACHING) — re-opens the same
        chatter-then-checkpoint flow finish_explaining would have, for this
        same activity."""
        self.transition_to(TeacherMode.AWAITING_ANSWER if self.budget() == 0 else TeacherMode.DEMONSTRATING)

    def advance_to_next_activity(self):
        """Only valid once the checkpoint was answered with understanding
        (mode is TRANSITIONING — call record_checkpoint_result(True) first).
        Moves to the next activity, if any, and resets this activity's
        per-activity counters."""
        if self.mode is not TeacherMode.TRANSITIONING:
            raise InvalidTransitionError("advance_to_next_activity requires mode TRANSITIONING")
        self.activity_index += 1
        self.autonomous_turns_used = 0
        if not self.is_complete():
            self.mode = TeacherMode.TEACHING

    def start_answering_question(self):
        """A student (or pool agent) asked something that isn't the
        checkpoint answer while a plan-driven lesson is otherwise mid-flow.
        The teacher answers it as an aside, then returns to whatever mode it
        came from."""
        self._mode_before_question = self.mode
        self.transition_to(TeacherMode.ANSWERING_QUESTION)

    def finish_answering_question(self):
        previous = getattr(self, "_mode_before_question", TeacherMode.AWAITING_ANSWER)
        self.mode = previous

    def homework(self) -> str:
        return (self.plan or {}).get("homework") or ""

    def should_deliver_homework(self) -> bool:
        return self.is_complete() and bool(self.homework()) and not self.homework_delivered

    def mark_homework_delivered(self):
        self.homework_delivered = True
