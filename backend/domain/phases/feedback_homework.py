"""Stage 6 sub-flow (diagram 6.1-6.5): immediate feedback, build homework
(the course project's next stage, if there is one), accept a submission,
grade it, and follow up on gaps before marking the lesson as passed."""

from dataclasses import dataclass, field
from enum import Enum

from domain.state_machine import StateMachine


class FeedbackState(Enum):
    GIVING_FEEDBACK = "giving_feedback"  # 6.1
    BUILDING_HOMEWORK = "building_homework"  # 6.2
    AWAITING_SUBMISSION = "awaiting_submission"  # 6.3
    GRADING = "grading"  # 6.4
    FOLLOWING_UP = "following_up"  # 6.5: gaps found -> re-practice
    DONE = "done"


@dataclass
class FeedbackHomeworkFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        FeedbackState.GIVING_FEEDBACK: {FeedbackState.BUILDING_HOMEWORK},
        FeedbackState.BUILDING_HOMEWORK: {FeedbackState.AWAITING_SUBMISSION},
        FeedbackState.AWAITING_SUBMISSION: {FeedbackState.GRADING},
        FeedbackState.GRADING: {FeedbackState.FOLLOWING_UP, FeedbackState.DONE},
        # After addressing gaps the student resubmits; or explicitly moves on anyway.
        FeedbackState.FOLLOWING_UP: {FeedbackState.AWAITING_SUBMISSION, FeedbackState.DONE},
        FeedbackState.DONE: set(),
    }

    state: FeedbackState = FeedbackState.GIVING_FEEDBACK
    homework: dict | None = None
    submissions: list = field(default_factory=list)
    grade: float | None = None
    gaps: list = field(default_factory=list)

    def is_done(self) -> bool:
        return self.state is FeedbackState.DONE
