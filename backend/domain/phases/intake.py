"""Stage 1 sub-flow (diagram 1.1-1.4): choose topic, gather context about
the student, diagnose starting level, hand off to syllabus building."""

from dataclasses import dataclass, field
from enum import Enum

from domain.state_machine import StateMachine


class IntakeState(Enum):
    CHOOSING_TOPIC = "choosing_topic"  # 1.1: topic, single lesson vs program, time budget, target depth
    GATHERING_CONTEXT = "gathering_context"  # 1.2: prior history, learning goal
    DIAGNOSING_LEVEL = "diagnosing_level"  # 1.3: explicit level, or a short diagnostic quiz
    READY = "ready"  # 1.4: everything gathered, hand off to SYLLABUS


@dataclass
class IntakeFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        IntakeState.CHOOSING_TOPIC: {IntakeState.GATHERING_CONTEXT},
        IntakeState.GATHERING_CONTEXT: {IntakeState.DIAGNOSING_LEVEL},
        # A level the student stated explicitly skips the diagnostic quiz.
        IntakeState.DIAGNOSING_LEVEL: {IntakeState.READY},
        IntakeState.READY: set(),
    }

    state: IntakeState = IntakeState.CHOOSING_TOPIC
    topic: str = ""
    single_lesson: bool = True
    time_budget_minutes: int | None = None
    target_depth: str | None = None  # "basics" | "practical" | "expert"
    starting_level: str | None = None  # "beginner" | "intermediate" | "expert"
    learning_goal: str = ""
    prior_lesson_ids: list = field(default_factory=list)

    def is_done(self) -> bool:
        return self.state is IntakeState.READY

    @classmethod
    def from_partial(cls, data: dict | None) -> "IntakeFlow":
        """Where intake stands, read off whatever the student has filled in.

        Intake happens before any session exists, so there is no server-side
        object to hold its state between requests — the form's values are the
        state. This derives the machine's position from them, so "which step
        is still missing" has one definition that the server enforces and the
        form mirrors, instead of the client and server each deciding.

        It only reports position; whether the values are *valid* is
        LearnerProfile.from_dict's job.
        """
        data = data or {}
        flow = cls()
        flow.topic = str(data.get("topic") or "").strip()
        flow.time_budget_minutes = data.get("time_budget_minutes")
        flow.target_depth = data.get("target_depth")
        flow.starting_level = data.get("starting_level")
        flow.learning_goal = str(data.get("goal") or "").strip()

        # Each step is entered only once the one before it is complete, so
        # the walk stops at the first missing piece.
        if not flow.topic:
            return flow
        flow.state = IntakeState.GATHERING_CONTEXT
        if flow.time_budget_minutes is None or flow.target_depth is None:
            return flow
        flow.state = IntakeState.DIAGNOSING_LEVEL
        if flow.starting_level is None:
            return flow
        flow.state = IntakeState.READY
        return flow
