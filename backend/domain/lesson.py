"""Lesson: the single owner of "where is this plan-driven lesson right now."

Before this class existed, that question was answered independently in at
least four places by combining raw booleans on Session (awaiting_user,
activity_teacher_explained, activity_index vs len(activities)). Those
derivations could — and did — drift apart.

Every state change goes through transition_to() (enforced against
teacher_mode.ALLOWED_TRANSITIONS) or one of the named methods below, which
themselves only ever call transition_to() — there is no other way to change
self.mode. Each named method documents, and asserts, which mode it requires
to be called from, instead of silently doing the wrong thing from the wrong
state.
"""

from dataclasses import dataclass

from domain.teacher_mode import InvalidTransitionError, TeacherMode, can_transition

DEFAULT_AUTONOMOUS_EXCHANGES = 1


@dataclass
class Lesson:
    plan: dict | None = None
    activity_index: int = 0
    mode: TeacherMode = TeacherMode.TEACHING
    autonomous_turns_used: int = 0
    homework_delivered: bool = False
    # Only meaningful while mode is ANSWERING_QUESTION: the mode to return to
    # once the aside question has been answered. A real dataclass field (not
    # an ad hoc attribute) so it round-trips through equality/repr/persistence
    # like everything else here.
    resume_mode: TeacherMode | None = None

    def __post_init__(self):
        if self.plan is None:
            # A plan-less ("review") session has no activities to be "in" —
            # TEACHING would be meaningless and ANSWERING_QUESTION wouldn't
            # know what to resume to. COMPLETED (terminal, answers questions
            # from anywhere) is the only mode that fits "there is no plan".
            self.mode = TeacherMode.COMPLETED
        elif self.activity_index >= len(self.activities):
            # Rehydrating a lesson that had already finished before this
            # process restarted — land in the same terminal state the live
            # path would have reached, not the default starting mode.
            self.mode = TeacherMode.COMPLETED

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

    def is_done(self) -> bool:
        """Uniform with every other phase sub-flow (domain/phases/), so
        CourseFlow can treat the live lesson like any other phase."""
        return self.is_complete()

    @property
    def expects_checkpoint_answer(self) -> bool:
        """True exactly when the student's next message should be treated as
        an answer to the current activity's checkpoint question, rather than
        a generic chat message or an aside question."""
        return self.mode is TeacherMode.AWAITING_ANSWER

    @property
    def autoplay_paused(self) -> bool:
        """True when the autonomous "beat" loop (lesson_plan.advance_lesson_stream)
        must stop and wait for the real student instead of scheduling another
        beat — either a checkpoint is pending an answer, or there's nothing
        left to teach."""
        return self.mode in (TeacherMode.AWAITING_ANSWER, TeacherMode.COMPLETED)

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
        """Call once the teacher has just taught the current activity's
        material for the first time. Requires mode TEACHING."""
        if self.mode is not TeacherMode.TEACHING:
            raise InvalidTransitionError("finish_explaining requires mode TEACHING")
        self.transition_to(TeacherMode.ASKING_CHECKPOINT if self.budget() == 0 else TeacherMode.DEMONSTRATING)

    def record_autonomous_turn(self):
        """One pool-agent 'beat' during the DEMONSTRATING phase has happened.
        Requires mode DEMONSTRATING. Moves on to ASKING_CHECKPOINT once the
        budget is spent; otherwise stays in DEMONSTRATING (a legal self-loop)."""
        if self.mode is not TeacherMode.DEMONSTRATING:
            raise InvalidTransitionError("record_autonomous_turn requires mode DEMONSTRATING")
        self.autonomous_turns_used += 1
        if self.budget_spent():
            self.transition_to(TeacherMode.ASKING_CHECKPOINT)

    def mark_checkpoint_asked(self):
        """Call once the checkpoint question has actually been sent to the
        student. Requires mode ASKING_CHECKPOINT."""
        self.transition_to(TeacherMode.AWAITING_ANSWER)

    def record_checkpoint_result(self, understood: bool):
        """Call once a real student has answered the current activity's
        checkpoint question. Requires mode AWAITING_ANSWER. understood=True
        readies the lesson to move to the next activity
        (advance_to_next_activity); understood=False stays on this activity
        and has the teacher re-teach it."""
        if understood:
            self.transition_to(TeacherMode.TRANSITIONING)
        else:
            self.transition_to(TeacherMode.RETEACHING)
            self.autonomous_turns_used = 0

    def retry_current_activity(self):
        """Call once the teacher has re-taught the activity after a
        misunderstood checkpoint. Requires mode RETEACHING. Re-opens the
        same chatter-then-checkpoint flow finish_explaining would have, for
        this same activity."""
        if self.mode is not TeacherMode.RETEACHING:
            raise InvalidTransitionError("retry_current_activity requires mode RETEACHING")
        self.transition_to(TeacherMode.ASKING_CHECKPOINT if self.budget() == 0 else TeacherMode.DEMONSTRATING)

    def advance_to_next_activity(self):
        """Only valid once the checkpoint was answered with understanding
        (mode TRANSITIONING — call record_checkpoint_result(True) first).
        Moves to the next activity, if any, and resets this activity's
        per-activity counters; lands in COMPLETED once none are left."""
        if self.mode is not TeacherMode.TRANSITIONING:
            raise InvalidTransitionError("advance_to_next_activity requires mode TRANSITIONING")
        self.activity_index += 1
        self.autonomous_turns_used = 0
        if self.is_complete():
            self.transition_to(TeacherMode.COMPLETED)
        else:
            self.transition_to(TeacherMode.TEACHING)

    def start_answering_question(self):
        """A student (or pool agent) asked something that isn't the
        checkpoint answer while the lesson is otherwise mid-flow. The
        teacher answers it as an aside, then returns to whatever mode it
        came from. Safe to call again while already answering a question —
        it will not overwrite the original resume_mode."""
        if self.mode is TeacherMode.ANSWERING_QUESTION:
            return
        self.resume_mode = self.mode
        self.transition_to(TeacherMode.ANSWERING_QUESTION)

    def finish_answering_question(self):
        """Requires mode ANSWERING_QUESTION, reached via start_answering_question."""
        if self.mode is not TeacherMode.ANSWERING_QUESTION or self.resume_mode is None:
            raise InvalidTransitionError("finish_answering_question requires an in-progress question")
        target, self.resume_mode = self.resume_mode, None
        self.transition_to(target)

    def homework(self) -> str:
        return (self.plan or {}).get("homework") or ""

    def should_deliver_homework(self) -> bool:
        return self.is_complete() and bool(self.homework()) and not self.homework_delivered

    def mark_homework_delivered(self):
        self.homework_delivered = True
