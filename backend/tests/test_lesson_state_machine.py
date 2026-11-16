"""Unit tests for the TeacherMode/Lesson state machine (domain/).

Pure — no Anthropic calls, no DB — so these run instantly and are the
regression net for the defects found in review: a lesson that could never
accept another message once it ended, a crash on a message sent during the
reteach window, a double-call bug in the aside-question handler, a counter
mutated before validating the transition, and inconsistent rehydration of a
finished/plan-less lesson.
"""

import pytest

from domain.lesson import Lesson
from domain.teacher_mode import InvalidTransitionError, TeacherMode


def make_plan(*, budgets=(1, 0), homework="hw"):
    return {
        "activities": [
            {"title": f"a{i}", "autonomous_exchanges": b, "checkpoint_question": f"q{i}"}
            for i, b in enumerate(budgets)
        ],
        "homework": homework,
    }


def advance_happy_path(lesson: Lesson):
    """Drives one activity from TEACHING to TRANSITIONING via the normal
    understood-on-first-try path, used as setup by several tests below."""
    lesson.finish_explaining()
    while lesson.mode is TeacherMode.DEMONSTRATING:
        lesson.record_autonomous_turn()
    lesson.mark_checkpoint_asked()
    lesson.record_checkpoint_result(True)


class TestHappyPath:
    def test_full_lesson_to_completion(self):
        lesson = Lesson(plan=make_plan())
        assert lesson.mode is TeacherMode.TEACHING

        advance_happy_path(lesson)
        assert lesson.mode is TeacherMode.TRANSITIONING
        lesson.advance_to_next_activity()
        assert lesson.mode is TeacherMode.TEACHING
        assert lesson.activity_index == 1
        assert not lesson.is_complete()

        advance_happy_path(lesson)
        lesson.advance_to_next_activity()
        assert lesson.mode is TeacherMode.COMPLETED
        assert lesson.is_complete()
        assert lesson.should_deliver_homework()
        lesson.mark_homework_delivered()
        assert not lesson.should_deliver_homework()

    def test_zero_budget_activity_skips_straight_to_checkpoint(self):
        lesson = Lesson(plan=make_plan(budgets=(0,)))
        lesson.finish_explaining()
        assert lesson.mode is TeacherMode.ASKING_CHECKPOINT

    def test_expects_checkpoint_answer_only_while_awaiting_answer(self):
        lesson = Lesson(plan=make_plan(budgets=(0,)))
        assert not lesson.expects_checkpoint_answer
        lesson.finish_explaining()
        assert not lesson.expects_checkpoint_answer
        lesson.mark_checkpoint_asked()
        assert lesson.expects_checkpoint_answer

    def test_autoplay_paused_only_while_awaiting_answer_or_complete(self):
        lesson = Lesson(plan=make_plan(budgets=(1,)))
        assert not lesson.autoplay_paused
        lesson.finish_explaining()
        assert not lesson.autoplay_paused  # DEMONSTRATING: more autonomous beats to go
        lesson.record_autonomous_turn()
        lesson.mark_checkpoint_asked()
        assert lesson.autoplay_paused


class TestMisunderstanding:
    def test_reteach_loop_resets_turn_counter_and_rejoins_normal_flow(self):
        lesson = Lesson(plan=make_plan(budgets=(2,)))
        lesson.finish_explaining()
        lesson.record_autonomous_turn()
        lesson.record_autonomous_turn()
        lesson.mark_checkpoint_asked()
        lesson.record_checkpoint_result(False)
        assert lesson.mode is TeacherMode.RETEACHING
        assert lesson.autonomous_turns_used == 0

        lesson.retry_current_activity()
        assert lesson.mode is TeacherMode.DEMONSTRATING
        lesson.record_autonomous_turn()
        lesson.record_autonomous_turn()
        lesson.mark_checkpoint_asked()
        lesson.record_checkpoint_result(True)
        assert lesson.mode is TeacherMode.TRANSITIONING

    def test_reteach_with_zero_budget_goes_straight_back_to_checkpoint(self):
        lesson = Lesson(plan=make_plan(budgets=(0,)))
        lesson.finish_explaining()
        lesson.mark_checkpoint_asked()
        lesson.record_checkpoint_result(False)
        lesson.retry_current_activity()
        assert lesson.mode is TeacherMode.ASKING_CHECKPOINT


class TestAsideQuestionsDoNotLoseWhereTheLessonWas:
    """Regression tests for the double-call bug and the reteach-window crash."""

    @pytest.mark.parametrize(
        "setup_mode", [m for m in TeacherMode if m is not TeacherMode.ANSWERING_QUESTION]
    )
    def test_question_from_every_mode_returns_to_the_same_mode(self, setup_mode):
        lesson = Lesson(plan=make_plan(budgets=(1,)))
        lesson.mode = setup_mode  # force into the mode under test directly
        lesson.start_answering_question()
        assert lesson.mode is TeacherMode.ANSWERING_QUESTION
        lesson.finish_answering_question()
        assert lesson.mode is setup_mode

    def test_double_start_does_not_overwrite_resume_mode(self):
        lesson = Lesson(plan=make_plan(budgets=(1,)))
        lesson.finish_explaining()
        assert lesson.mode is TeacherMode.DEMONSTRATING
        lesson.start_answering_question()
        lesson.start_answering_question()  # must be a no-op, not re-capture ANSWERING_QUESTION
        lesson.finish_answering_question()
        assert lesson.mode is TeacherMode.DEMONSTRATING

    def test_finish_without_start_raises(self):
        lesson = Lesson(plan=make_plan())
        with pytest.raises(InvalidTransitionError):
            lesson.finish_answering_question()


class TestEdgeCasesThatUsedToCrash:
    def test_message_after_lesson_already_completed(self):
        lesson = Lesson(plan=make_plan(budgets=(0,)))
        advance_happy_path(lesson)
        lesson.advance_to_next_activity()
        assert lesson.mode is TeacherMode.COMPLETED

        # Must not raise — this used to be an unreachable terminal trap.
        lesson.start_answering_question()
        lesson.finish_answering_question()
        assert lesson.mode is TeacherMode.COMPLETED

    def test_rehydrating_an_already_finished_lesson_lands_in_completed(self):
        plan = make_plan(budgets=(1, 0))
        lesson = Lesson(plan=plan, activity_index=len(plan["activities"]))
        assert lesson.mode is TeacherMode.COMPLETED
        assert lesson.is_complete()

    def test_plan_less_review_session_is_complete_and_answers_questions(self):
        lesson = Lesson(plan=None)
        assert lesson.is_complete()
        assert lesson.mode is TeacherMode.COMPLETED
        lesson.start_answering_question()
        lesson.finish_answering_question()
        assert lesson.mode is TeacherMode.COMPLETED


class TestGuardsRejectIllegalCalls:
    def test_record_autonomous_turn_requires_demonstrating_and_does_not_mutate_on_failure(self):
        lesson = Lesson(plan=make_plan(budgets=(1,)))
        assert lesson.mode is TeacherMode.TEACHING
        with pytest.raises(InvalidTransitionError):
            lesson.record_autonomous_turn()
        assert lesson.autonomous_turns_used == 0  # must not have incremented before raising

    def test_finish_explaining_requires_teaching(self):
        lesson = Lesson(plan=make_plan())
        lesson.finish_explaining()
        with pytest.raises(InvalidTransitionError):
            lesson.finish_explaining()

    def test_retry_current_activity_requires_reteaching(self):
        lesson = Lesson(plan=make_plan())
        with pytest.raises(InvalidTransitionError):
            lesson.retry_current_activity()

    def test_advance_to_next_activity_requires_transitioning(self):
        lesson = Lesson(plan=make_plan())
        with pytest.raises(InvalidTransitionError):
            lesson.advance_to_next_activity()
