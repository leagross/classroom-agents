"""Generic reusable state-machine building block.

TeacherMode/Lesson (the one piece of this that existed before the "it's all
state machines" decision) hand-rolled its own transition_to/ALLOWED_TRANSITIONS
pattern — it's left as-is since it's already tested. Every state machine
added after it (the per-phase flows under domain/phases/) declares its
ALLOWED_TRANSITIONS once and inherits guarded transitions from here instead
of duplicating that enforcement in each class.
"""

from dataclasses import dataclass


class InvalidStateTransitionError(Exception):
    pass


class StateMachine:
    """Subclasses set a class-level ALLOWED_TRANSITIONS: dict[Enum, set[Enum]]
    and hold the current value in self.state."""

    ALLOWED_TRANSITIONS: dict = {}
    state = None

    def can_transition(self, target) -> bool:
        return target in self.ALLOWED_TRANSITIONS.get(self.state, set())

    def transition_to(self, target):
        if not self.can_transition(target):
            raise InvalidStateTransitionError(
                f"{type(self).__name__}: {self.state} -> {target} is not allowed"
            )
        self.state = target
