"""CourseFlow: the top of the state-machine hierarchy.

Owns which of the 7 phases (course_phase.CoursePhase) one lesson's journey
is in, and one sub-flow per phase that owns that phase's finer-grained
states (the sub-steps under each stage in the flow diagram). Moving to the
next phase is only allowed once the current sub-flow reports is_done() —
nothing can skip ahead, e.g. into QUESTIONS before the live lesson actually
taught the material.

Adding a new phase means: a new CoursePhase value, a new sub-flow class with
an is_done() method, and one entry in _SUBFLOW_FACTORIES. Nothing else
changes.
"""

from dataclasses import dataclass, field

from domain.course_phase import CoursePhase, next_phase
from domain.lesson import Lesson
from domain.phases.feedback_homework import FeedbackHomeworkFlow
from domain.phases.intake import IntakeFlow
from domain.phases.practice import PracticeFlow
from domain.phases.questions import QuestionsFlow
from domain.phases.summary import SummaryFlow
from domain.phases.syllabus import SyllabusFlow
from domain.state_machine import InvalidStateTransitionError

_SUBFLOW_FACTORIES = {
    CoursePhase.INTAKE: IntakeFlow,
    CoursePhase.SYLLABUS: SyllabusFlow,
    CoursePhase.LIVE_LESSON: Lesson,
    CoursePhase.QUESTIONS: QuestionsFlow,
    CoursePhase.PRACTICE: PracticeFlow,
    CoursePhase.FEEDBACK_HOMEWORK: FeedbackHomeworkFlow,
    CoursePhase.SUMMARY: SummaryFlow,
}


@dataclass
class CourseFlow:
    phase: CoursePhase = CoursePhase.INTAKE
    subflows: dict = field(default_factory=dict)

    @property
    def current(self):
        """The active phase's sub-flow, created on first access."""
        if self.phase not in self.subflows:
            self.subflows[self.phase] = _SUBFLOW_FACTORIES[self.phase]()
        return self.subflows[self.phase]

    def is_finished(self) -> bool:
        return next_phase(self.phase) is None and self.current.is_done()

    def advance_phase(self, next_subflow=None):
        """Move to the next phase. Requires the current sub-flow to be done.
        next_subflow lets the caller hand in a pre-built sub-flow for the
        new phase (e.g. a Lesson built from the approved syllabus' plan)
        instead of a default-constructed one."""
        if not self.current.is_done():
            raise InvalidStateTransitionError(f"cannot leave {self.phase}: its sub-flow is not done")
        target = next_phase(self.phase)
        if target is None:
            raise InvalidStateTransitionError(f"{self.phase} is the last phase")
        self.phase = target
        if next_subflow is not None:
            self.subflows[target] = next_subflow
