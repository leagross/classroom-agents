"""Stage 7 sub-flow (diagram 7.1-7.3): record progress, then either move on
to the next lesson in the syllabus or close out the whole course."""

from dataclasses import dataclass
from enum import Enum

from domain.state_machine import StateMachine


class SummaryState(Enum):
    UPDATING_PROGRESS = "updating_progress"  # 7.1
    NEXT_LESSON = "next_lesson"  # 7.2: more lessons in the syllabus
    COURSE_SUMMARY = "course_summary"  # 7.3: that was the last lesson
    DONE = "done"


@dataclass
class SummaryFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        SummaryState.UPDATING_PROGRESS: {SummaryState.NEXT_LESSON, SummaryState.COURSE_SUMMARY},
        SummaryState.NEXT_LESSON: {SummaryState.DONE},
        SummaryState.COURSE_SUMMARY: {SummaryState.DONE},
        SummaryState.DONE: set(),
    }

    state: SummaryState = SummaryState.UPDATING_PROGRESS

    def is_done(self) -> bool:
        return self.state is SummaryState.DONE
