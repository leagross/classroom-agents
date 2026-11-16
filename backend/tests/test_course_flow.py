"""Tests for the top-level CourseFlow and the per-phase sub-flows."""

import pytest

from domain.course_flow import CourseFlow
from domain.course_phase import CoursePhase
from domain.lesson import Lesson
from domain.phases.feedback_homework import FeedbackState
from domain.phases.intake import IntakeState
from domain.phases.practice import PracticeState, PracticeTrack
from domain.phases.questions import QueuedQuestion, QuestionsState
from domain.phases.summary import SummaryState
from domain.phases.syllabus import SyllabusState
from domain.state_machine import InvalidStateTransitionError


def finish_intake(flow):
    f = flow.current
    f.transition_to(IntakeState.GATHERING_CONTEXT)
    f.transition_to(IntakeState.DIAGNOSING_LEVEL)
    f.transition_to(IntakeState.READY)


def finish_syllabus(flow):
    f = flow.current
    for s in (
        SyllabusState.SCOPING, SyllabusState.RESEARCHING_SOURCES, SyllabusState.BUILDING_SYLLABUS,
        SyllabusState.AWAITING_APPROVAL, SyllabusState.DEFINING_PROJECT,
        SyllabusState.BUILDING_PRESENTATIONS, SyllabusState.READY,
    ):
        f.transition_to(s)


class TestCourseFlow:
    def test_starts_in_intake(self):
        flow = CourseFlow()
        assert flow.phase is CoursePhase.INTAKE
        assert flow.current.state is IntakeState.CHOOSING_TOPIC

    def test_cannot_leave_a_phase_before_its_subflow_is_done(self):
        flow = CourseFlow()
        with pytest.raises(InvalidStateTransitionError):
            flow.advance_phase()
        assert flow.phase is CoursePhase.INTAKE

    def test_full_journey_through_all_seven_phases(self):
        flow = CourseFlow()
        finish_intake(flow)
        flow.advance_phase()
        assert flow.phase is CoursePhase.SYLLABUS

        finish_syllabus(flow)
        plan = {"activities": [{"title": "a", "autonomous_exchanges": 0, "checkpoint_question": "q"}]}
        flow.advance_phase(next_subflow=Lesson(plan=plan))
        assert flow.phase is CoursePhase.LIVE_LESSON
        lesson = flow.current
        lesson.finish_explaining()
        lesson.mark_checkpoint_asked()
        lesson.record_checkpoint_result(True)
        lesson.advance_to_next_activity()
        assert lesson.is_done()

        flow.advance_phase()
        assert flow.phase is CoursePhase.QUESTIONS
        flow.current.close()

        flow.advance_phase()
        assert flow.phase is CoursePhase.PRACTICE
        p = flow.current
        p.choose_track(PracticeTrack.THEORY)
        p.transition_to(PracticeState.ATTEMPTING)
        p.transition_to(PracticeState.FINAL_CHECK)
        p.transition_to(PracticeState.DONE)

        flow.advance_phase()
        assert flow.phase is CoursePhase.FEEDBACK_HOMEWORK
        fb = flow.current
        for s in (FeedbackState.BUILDING_HOMEWORK, FeedbackState.AWAITING_SUBMISSION,
                  FeedbackState.GRADING, FeedbackState.DONE):
            fb.transition_to(s)

        flow.advance_phase()
        assert flow.phase is CoursePhase.SUMMARY
        flow.current.transition_to(SummaryState.COURSE_SUMMARY)
        flow.current.transition_to(SummaryState.DONE)
        assert flow.is_finished()
        with pytest.raises(InvalidStateTransitionError):
            flow.advance_phase()


class TestSubflowRules:
    def test_rejected_syllabus_goes_back_to_rebuild(self):
        flow = CourseFlow(phase=CoursePhase.SYLLABUS)
        f = flow.current
        for s in (SyllabusState.SCOPING, SyllabusState.RESEARCHING_SOURCES,
                  SyllabusState.BUILDING_SYLLABUS, SyllabusState.AWAITING_APPROVAL):
            f.transition_to(s)
        f.transition_to(SyllabusState.BUILDING_SYLLABUS)
        assert f.state is SyllabusState.BUILDING_SYLLABUS

    def test_syllabus_cannot_skip_research(self):
        flow = CourseFlow(phase=CoursePhase.SYLLABUS)
        flow.current.transition_to(SyllabusState.SCOPING)
        with pytest.raises(InvalidStateTransitionError):
            flow.current.transition_to(SyllabusState.BUILDING_SYLLABUS)

    def test_question_queue_puts_real_student_first(self):
        flow = CourseFlow(phase=CoursePhase.QUESTIONS)
        q = flow.current
        q.enqueue(QueuedQuestion("agent question", from_real_student=False))
        q.enqueue(QueuedQuestion("student question", from_real_student=True))
        assert q.start_next().text == "student question"

    def test_question_not_understood_is_answered_again(self):
        flow = CourseFlow(phase=CoursePhase.QUESTIONS)
        q = flow.current
        q.enqueue(QueuedQuestion("why?", from_real_student=True))
        q.start_next()
        q.finish_answer()
        q.record_understanding(False)
        assert q.state is QuestionsState.ANSWERING
        q.finish_answer()
        q.record_understanding(True)
        assert q.state is QuestionsState.OPEN
        assert [a.text for a in q.answered] == ["why?"]

    def test_failed_final_practice_check_returns_to_attempting(self):
        flow = CourseFlow(phase=CoursePhase.PRACTICE)
        p = flow.current
        p.choose_track(PracticeTrack.CODE)
        p.transition_to(PracticeState.ATTEMPTING)
        p.transition_to(PracticeState.FINAL_CHECK)
        p.transition_to(PracticeState.ATTEMPTING)
        assert p.state is PracticeState.ATTEMPTING

    def test_homework_gaps_loop_back_to_resubmission(self):
        flow = CourseFlow(phase=CoursePhase.FEEDBACK_HOMEWORK)
        fb = flow.current
        for s in (FeedbackState.BUILDING_HOMEWORK, FeedbackState.AWAITING_SUBMISSION,
                  FeedbackState.GRADING, FeedbackState.FOLLOWING_UP, FeedbackState.AWAITING_SUBMISSION):
            fb.transition_to(s)
        assert fb.state is FeedbackState.AWAITING_SUBMISSION
