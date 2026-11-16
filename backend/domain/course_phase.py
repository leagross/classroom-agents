"""The top-level state machine for one lesson's journey, per the 7-stage
flow diagram: INTAKE(1) -> SYLLABUS(2) -> LIVE_LESSON(3) -> QUESTIONS(4) ->
PRACTICE(5) -> FEEDBACK_HOMEWORK(6) -> SUMMARY(7). Linear, one-directional —
CourseFlow (course_flow.py) is the only thing that advances it, and each
phase's own sub-flow (domain/phases/) owns the finer-grained states listed
under that stage in the diagram (e.g. stage 3's sub-flow is TeacherMode/Lesson).
"""

from enum import Enum


class CoursePhase(Enum):
    INTAKE = "intake"  # 1: choose topic, gather context, diagnose level
    SYLLABUS = "syllabus"  # 2: research + build syllabus + project + presentations
    LIVE_LESSON = "live_lesson"  # 3: the live simulated lesson (TeacherMode/Lesson)
    QUESTIONS = "questions"  # 4: ordered question queue after the explanation
    PRACTICE = "practice"  # 5: exercises, code-or-theory
    FEEDBACK_HOMEWORK = "feedback_homework"  # 6: feedback + homework + grading
    SUMMARY = "summary"  # 7: progress update, next lesson or course summary


_ORDER = list(CoursePhase)

ALLOWED_PHASE_TRANSITIONS: dict[CoursePhase, set[CoursePhase]] = {
    phase: ({_ORDER[i + 1]} if i + 1 < len(_ORDER) else set())
    for i, phase in enumerate(_ORDER)
}


def next_phase(current: CoursePhase) -> CoursePhase | None:
    targets = ALLOWED_PHASE_TRANSITIONS.get(current, set())
    return next(iter(targets), None)
