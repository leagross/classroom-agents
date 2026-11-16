"""The teacher's instructions are behaviour, so they get tests too.

These assert the teaching contract the lesson is built on: explain before
showing, assume no prior knowledge, and — when the student says they are
lost — work out what specifically is unclear instead of repeating the
explanation that already failed.
"""

import orchestrator
import session_state
from domain.lesson import Lesson
from domain.teacher_actions import (
    AnswerQuestionAction,
    CheckpointFeedbackAction,
    ExplainAction,
    ReteachAction,
)

PLAN = {
    "goals": ["g"],
    "activities": [
        {
            "stage": "teaching",
            "title": "נגזרות",
            "summary": "הגדרת הנגזרת",
            "autonomous_exchanges": 0,
            "checkpoint_question": "מה הנגזרת של x²?",
        }
    ],
    "homework": "",
}


def a_session():
    return session_state.create_session("חשבון דיפרנציאלי", pool_keys=["dani", "deep_diver"], plan=PLAN)


class TestExplainsBeforeShowing:
    def test_explain_demands_idea_before_notation(self):
        session = a_session()
        prompt = ExplainAction().build_prompt(session, session.lesson)
        assert "קודם מסבירים, ורק אחר כך מציגים" in prompt
        assert "לפני שהסברת" in prompt

    def test_explain_assumes_no_prior_knowledge(self):
        session = a_session()
        prompt = ExplainAction().build_prompt(session, session.lesson)
        assert "לא מכיר את הנושא בכלל" in prompt
        assert "אל תניח שום ידע קודם" in prompt

    def test_explain_bans_dismissive_phrasing(self):
        """"As you know" / "obviously" assume exactly the background the
        student is here because they lack."""
        session = a_session()
        prompt = ExplainAction().build_prompt(session, session.lesson)
        for phrase in ("כידוע", "כמו שאתה יודע"):
            assert phrase in prompt  # named in the prompt as forbidden

    def test_new_material_is_detailed_and_covered_material_is_brief(self):
        session = a_session()
        prompt = ExplainAction().build_prompt(session, session.lesson)
        assert "הסבר בפירוט" in prompt
        assert "תזכורת קצרה" in prompt


class TestDiagnosesMisunderstanding:
    def test_reteach_requires_identifying_what_was_unclear_first(self):
        session = a_session()
        prompt = ReteachAction().build_prompt(session, session.lesson)
        assert "זהה מתוך דבריו מה בדיוק" in prompt
        # and must cope with a bare "I don't get it"
        assert "לא הבנתי" in prompt

    def test_reteach_must_not_repeat_the_route_that_failed(self):
        session = a_session()
        prompt = ReteachAction().build_prompt(session, session.lesson)
        assert "אל תחזור על אותן מילים" in prompt
        assert "לא זו שכבר השתמשת בה" in prompt

    def test_reteach_offers_several_different_routes(self):
        session = a_session()
        prompt = ReteachAction().build_prompt(session, session.lesson)
        for route in ("אנלוגיה", "דוגמה", "צעדים קטנים"):
            assert route in prompt

    def test_reteach_targets_only_the_part_that_failed(self):
        session = a_session()
        prompt = ReteachAction().build_prompt(session, session.lesson)
        assert "רק את החלק שלא הובן" in prompt

    def test_saying_not_understood_mid_lesson_also_diagnoses(self):
        """A student can say it at any point, not only at a checkpoint."""
        session = a_session()
        prompt = AnswerQuestionAction().build_prompt(session, session.lesson)
        assert "אל תחזור על ההסבר הקודם כלשונו" in prompt
        assert "זהה קודם מתוך דבריו" in prompt

    def test_review_session_question_still_carries_the_contract(self):
        session = session_state.create_session("נושא", pool_keys=["dani", "deep_diver"], plan=None)
        prompt = AnswerQuestionAction().build_prompt(session, session.lesson)
        assert "אל תניח שום ידע קודם" in prompt

    def test_checkpoint_feedback_pinpoints_the_gap(self):
        session = a_session()
        prompt = CheckpointFeedbackAction().build_prompt(session, session.lesson)
        assert "מה בדיוק חסר או שגוי" in prompt


class TestTheStudentsWordsReachTheTeacher:
    """Diagnosis is only possible if what the student wrote is actually in
    the prompt — the transcript is what carries it."""

    def test_student_message_is_in_the_reteach_prompt(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, "תקין")])
        session = a_session()
        session_state.remember(
            session,
            session_state.ChatMessage("user", "את/ה", "#111827", "לא הבנתי מה זה גבול"),
        )
        prompt = ReteachAction().build_prompt(session, session.lesson)
        assert "לא הבנתי מה זה גבול" in prompt
