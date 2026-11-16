"""Stage 4 sub-flow (diagram 4.1-4.5): an ordered question queue, opened
only after the material was taught — one question at a time, the real
student's questions first, then verify understanding of each answer."""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from domain.state_machine import StateMachine


class QuestionsState(Enum):
    OPEN = "open"  # 4.1: questions invited, queue may be empty
    ANSWERING = "answering"  # 4.3: teacher answering the head of the queue
    VERIFYING_UNDERSTANDING = "verifying_understanding"  # 4.4: did the real student get it?
    CLOSED = "closed"  # 4.5: no more questions, move to practice


@dataclass
class QueuedQuestion:
    text: str
    from_real_student: bool
    off_topic: bool = False


@dataclass
class QuestionsFlow(StateMachine):
    ALLOWED_TRANSITIONS = {
        QuestionsState.OPEN: {QuestionsState.ANSWERING, QuestionsState.CLOSED},
        QuestionsState.ANSWERING: {QuestionsState.VERIFYING_UNDERSTANDING},
        # Not understood -> answer again; understood -> next question or close.
        QuestionsState.VERIFYING_UNDERSTANDING: {QuestionsState.ANSWERING, QuestionsState.OPEN},
        QuestionsState.CLOSED: set(),
    }

    state: QuestionsState = QuestionsState.OPEN
    queue: deque = field(default_factory=deque)
    answered: list = field(default_factory=list)  # kept for homework building (4.5)
    current: QueuedQuestion | None = None

    def enqueue(self, question: QueuedQuestion):
        # 4.2: the real student's questions take priority over pool agents'.
        if question.from_real_student:
            self.queue.appendleft(question)
        else:
            self.queue.append(question)

    def start_next(self) -> QueuedQuestion | None:
        if not self.queue:
            return None
        self.current = self.queue.popleft()
        self.transition_to(QuestionsState.ANSWERING)
        return self.current

    def finish_answer(self):
        self.transition_to(QuestionsState.VERIFYING_UNDERSTANDING)

    def record_understanding(self, understood: bool):
        if understood:
            self.answered.append(self.current)
            self.current = None
            self.transition_to(QuestionsState.OPEN)
        else:
            self.transition_to(QuestionsState.ANSWERING)

    def close(self):
        self.transition_to(QuestionsState.CLOSED)

    def is_done(self) -> bool:
        return self.state is QuestionsState.CLOSED
