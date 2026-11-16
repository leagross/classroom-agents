"""Stage 5 sub-flow (diagram 5.1-5.5): pick the code or theory track, build
an exercise from what was actually taught, let the student attempt it, then
a final understanding check."""

from dataclasses import dataclass
from enum import Enum

from domain.state_machine import StateMachine


class PracticeTrack(Enum):
    CODE = "code"  # 5.3: runs in a sandbox
    THEORY = "theory"  # 5.4: written exercises


class PracticeState(Enum):
    IDENTIFYING_TRACK = "identifying_track"  # 5.1
    BUILDING_EXERCISE = "building_exercise"  # 5.2: from goal, what was taught, weak checkpoints, level, project
    ATTEMPTING = "attempting"  # 5.3 / 5.4: the student works on it
    FINAL_CHECK = "final_check"  # 5.5
    DONE = "done"


@dataclass
class PracticeFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        PracticeState.IDENTIFYING_TRACK: {PracticeState.BUILDING_EXERCISE},
        PracticeState.BUILDING_EXERCISE: {PracticeState.ATTEMPTING},
        PracticeState.ATTEMPTING: {PracticeState.ATTEMPTING, PracticeState.FINAL_CHECK},
        # A failed final check sends the student back to another attempt.
        PracticeState.FINAL_CHECK: {PracticeState.ATTEMPTING, PracticeState.DONE},
        PracticeState.DONE: set(),
    }

    state: PracticeState = PracticeState.IDENTIFYING_TRACK
    track: PracticeTrack | None = None
    exercise: dict | None = None

    def choose_track(self, track: PracticeTrack):
        self.track = track
        self.transition_to(PracticeState.BUILDING_EXERCISE)

    def is_done(self) -> bool:
        return self.state is PracticeState.DONE
