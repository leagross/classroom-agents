"""Stage 2 sub-flow (diagram 2.1-2.7): research the topic and build the
syllabus, the course-spanning project, and the per-lesson presentations."""

from dataclasses import dataclass, field
from enum import Enum

from domain.state_machine import StateMachine


class SyllabusState(Enum):
    UNDERSTANDING_GOAL = "understanding_goal"  # 2.1: goal, sub-topics, prerequisites
    SCOPING = "scoping"  # 2.2: level, breadth, depth
    RESEARCHING_SOURCES = "researching_sources"  # 2.3: find and filter external sources
    BUILDING_SYLLABUS = "building_syllabus"  # 2.4: order sub-topics into lessons with goals + checkpoints
    AWAITING_APPROVAL = "awaiting_approval"  # 2.5: student reviews/edits the proposed syllabus
    DEFINING_PROJECT = "defining_project"  # 2.6: one project spanning the course, staged per lesson
    BUILDING_PRESENTATIONS = "building_presentations"  # 2.7: slides per lesson (built lazily)
    READY = "ready"


@dataclass
class SyllabusFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        SyllabusState.UNDERSTANDING_GOAL: {SyllabusState.SCOPING},
        SyllabusState.SCOPING: {SyllabusState.RESEARCHING_SOURCES},
        SyllabusState.RESEARCHING_SOURCES: {SyllabusState.BUILDING_SYLLABUS},
        SyllabusState.BUILDING_SYLLABUS: {SyllabusState.AWAITING_APPROVAL},
        # Rejecting the proposal sends it back to be rebuilt, not forward.
        SyllabusState.AWAITING_APPROVAL: {SyllabusState.BUILDING_SYLLABUS, SyllabusState.DEFINING_PROJECT},
        SyllabusState.DEFINING_PROJECT: {SyllabusState.BUILDING_PRESENTATIONS},
        SyllabusState.BUILDING_PRESENTATIONS: {SyllabusState.READY},
        SyllabusState.READY: set(),
    }

    state: SyllabusState = SyllabusState.UNDERSTANDING_GOAL
    goal: str = ""
    sub_topics: list = field(default_factory=list)
    prerequisites: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    lessons: list = field(default_factory=list)  # [{"title", "summary", "goal", "checkpoint_question"}]

    def is_done(self) -> bool:
        return self.state is SyllabusState.READY
