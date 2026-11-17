"""End-to-end tests of the one pipeline, with a fake model.

These cover the behaviours the rewrite was actually for:
  * a stray question mid-activity must NOT skip the rest of the activity
    (the old code advanced the lesson after every user message)
  * the streaming and non-streaming routes must agree, since they now run
    the same generator (the old non-streaming path skipped checkpoint
    handling entirely)
  * a checkpoint answer that shows misunderstanding must re-teach, not move on
  * an unparseable verdict must fall back to re-teaching, not to "understood"
  * a message after the lesson is over must not crash
"""

import orchestrator
import session_state
from domain.teacher_actions import RETEACH_MARKER, UNDERSTOOD_MARKER
from domain.teacher_mode import TeacherMode
from tests.conftest import is_verifier

PLAN = {
    "goals": ["g"],
    "activities": [
        {"stage": "opening", "title": "פעילות א", "summary": "s1", "autonomous_exchanges": 1, "checkpoint_question": "שאלת בדיקה א?"},
        {"stage": "summary", "title": "פעילות ב", "summary": "s2", "autonomous_exchanges": 0, "checkpoint_question": "שאלת בדיקה ב?"},
    ],
    "homework": "שיעורי בית לדוגמה",
}


def script(teacher_reply="הסבר של המורה.", verdict=None):
    """Verifier always passes; the teacher's reply optionally carries a
    checkpoint verdict marker."""
    reply = teacher_reply if verdict is None else f"{teacher_reply}\n{verdict}"
    return [
        (is_verifier, "תקין"),
        (lambda s, p: True, reply),
    ]


def new_session(plan=PLAN):
    return session_state.create_session("נושא בדיקה", pool_keys=["dani", "deep_diver"], plan=plan)


def drive_to_checkpoint(session, fake_anthropic):
    """Run autonomous beats until the lesson is waiting on the student."""
    fake_anthropic(script())
    for _ in range(10):
        if session.lesson.autoplay_paused:
            break
        list(orchestrator.autonomous_beat_events(session))
    return session


class TestAutonomousBeats:
    def test_beats_walk_teach_chatter_then_ask_checkpoint(self, fake_anthropic):
        fake_anthropic(script())
        session = new_session()
        assert session.lesson.mode is TeacherMode.TEACHING

        list(orchestrator.autonomous_beat_events(session))
        assert session.lesson.mode is TeacherMode.DEMONSTRATING

        list(orchestrator.autonomous_beat_events(session))
        assert session.lesson.mode is TeacherMode.ASKING_CHECKPOINT

        events = list(orchestrator.autonomous_beat_events(session))
        assert session.lesson.mode is TeacherMode.AWAITING_ANSWER
        done = events[-1]
        assert done["continue"] is False and done["awaiting_user"] is True
        # The checkpoint question is the plan's own text, delivered verbatim.
        assert any(e.get("text") == "שאלת בדיקה א?" for e in events)

    def test_teaching_beat_emits_board_notes_separately_from_speech(self, fake_anthropic):
        fake_anthropic([
            (is_verifier, "תקין"),
            (lambda s, p: True, "ההסבר המדובר.\n---BOARD---\nנקודה א\nנקודה ב"),
        ])
        session = new_session()
        events = list(orchestrator.autonomous_beat_events(session))
        spoken = [e["text"] for e in events if e.get("type") == "token"]
        board = [e["text"] for e in events if e.get("type") == "board"]
        assert spoken == ["ההסבר המדובר."]
        assert board == ["נקודה א\nנקודה ב"]

    def test_paused_lesson_produces_no_new_speech(self, fake_anthropic):
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        events = list(orchestrator.autonomous_beat_events(session))
        assert [e["type"] for e in events] == ["done"]


class TestStrayQuestionMidActivity:
    """The real user-visible bug: the old code called advance_after_checkpoint
    unconditionally, so any message sent while the classroom was mid-activity
    silently skipped the rest of that activity."""

    def test_question_during_chatter_does_not_advance_the_lesson(self, fake_anthropic):
        fake_anthropic(script())
        session = new_session()
        list(orchestrator.autonomous_beat_events(session))  # teach
        assert session.lesson.mode is TeacherMode.DEMONSTRATING
        index_before = session.lesson.activity_index

        list(orchestrator.user_message_events(session, "רגע, לא הבנתי משהו"))

        assert session.lesson.activity_index == index_before
        assert session.lesson.mode is TeacherMode.DEMONSTRATING

    def test_question_while_teaching_returns_to_teaching(self, fake_anthropic):
        fake_anthropic(script())
        session = new_session()
        assert session.lesson.mode is TeacherMode.TEACHING
        list(orchestrator.user_message_events(session, "שאלה מקדימה"))
        assert session.lesson.mode is TeacherMode.TEACHING
        assert session.lesson.activity_index == 0


class TestCheckpointAnswers:
    def test_understood_answer_advances_to_next_activity(self, fake_anthropic):
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("כל הכבוד, בדיוק.", verdict=UNDERSTOOD_MARKER))

        list(orchestrator.user_message_events(session, "התשובה שלי"))

        assert session.lesson.activity_index == 1
        assert session.lesson.mode is TeacherMode.TEACHING

    def test_misunderstood_answer_reteaches_the_same_activity(self, fake_anthropic):
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("לא בדיוק, בוא ננסה שוב.", verdict=RETEACH_MARKER))

        events = list(orchestrator.user_message_events(session, "תשובה שגויה"))

        assert session.lesson.activity_index == 0
        assert session.lesson.mode is TeacherMode.RETEACHING
        # No classroom chatter while the student is mid-struggle.
        assert [e for e in events if e.get("key") in ("dani", "deep_diver")] == []
        assert events[-1]["continue"] is True

        # The next beat re-teaches rather than re-asking the question.
        fake_anthropic(script("הסבר חוזר מזווית אחרת."))
        list(orchestrator.autonomous_beat_events(session))
        assert session.lesson.mode in (TeacherMode.DEMONSTRATING, TeacherMode.ASKING_CHECKPOINT)

    def test_unparseable_verdict_falls_back_to_reteaching(self, fake_anthropic):
        """The old code's worst silent default: a missing marker meant
        "understood", so a formatting slip advanced the lesson past material
        the student hadn't grasped."""
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("משוב בלי שורת הכרעה בכלל."))  # no marker, ever

        list(orchestrator.user_message_events(session, "תשובה"))

        assert session.lesson.mode is TeacherMode.RETEACHING
        assert session.lesson.activity_index == 0

    def test_homework_is_delivered_once_at_the_end(self, fake_anthropic):
        session = new_session()
        # First activity
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("טוב.", verdict=UNDERSTOOD_MARKER))
        list(orchestrator.user_message_events(session, "תשובה א"))
        # Second (last) activity
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("מצוין.", verdict=UNDERSTOOD_MARKER))
        events = list(orchestrator.user_message_events(session, "תשובה ב"))

        assert session.lesson.is_complete()
        assert any(e.get("text") == PLAN["homework"] for e in events)
        assert session.lesson.homework_delivered

        # A further message must not re-deliver it, and must not crash.
        fake_anthropic(script("תשובה נוספת."))
        more = list(orchestrator.user_message_events(session, "עוד שאלה"))
        assert not any(e.get("text") == PLAN["homework"] for e in more)
        assert not any(e.get("type") == "error" for e in more)


class TestBothRoutesAgree:
    """The documented bug: /api/message and /api/message/stream were two
    hand-maintained implementations, and only the streaming one implemented
    checkpoint handling. They now share one generator."""

    def _advance_via(self, use_streaming, fake_anthropic):
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("נכון מאוד.", verdict=UNDERSTOOD_MARKER))
        if use_streaming:
            list(orchestrator.user_message_events(session, "תשובה"))
        else:
            orchestrator.handle_user_message(session, "תשובה")
        return session.lesson

    def test_streaming_and_non_streaming_reach_the_same_state(self, fake_anthropic):
        streamed = self._advance_via(True, fake_anthropic)
        drained = self._advance_via(False, fake_anthropic)
        assert (streamed.activity_index, streamed.mode) == (drained.activity_index, drained.mode)
        assert drained.activity_index == 1

    def test_non_streaming_returns_the_teacher_and_classroom_replies(self, fake_anthropic):
        session = new_session()
        drive_to_checkpoint(session, fake_anthropic)
        fake_anthropic(script("נכון.", verdict=UNDERSTOOD_MARKER))
        replies = orchestrator.handle_user_message(session, "תשובה")
        assert [r.agent_key for r in replies][0] == "teacher"
        assert len(replies) >= 2  # teacher + at least one pool agent


class TestReviewSession:
    def test_plan_less_session_just_answers(self, fake_anthropic):
        fake_anthropic(script("תשובת המורה."))
        session = new_session(plan=None)
        assert session.lesson.is_complete()

        events = list(orchestrator.user_message_events(session, "שאלה חופשית"))

        assert not any(e.get("type") == "error" for e in events)
        assert session.lesson.activity_index == 0
        assert events[-1]["awaiting_user"] is True


class TestPlanPresentationFlag:
    """generate_lesson_plan must never let a malformed flag turn slides on."""

    def _plan_json(self, presentation_literal):
        return (
            '{"goals":["g"],"activities":[{"stage":"opening","title":"t","summary":"s",'
            '"autonomous_exchanges":1,"checkpoint_question":"q"}],"homework":"h",'
            f'"presentation":{presentation_literal}}}'
        )

    def test_true_boolean_is_kept(self, fake_anthropic):
        import lesson_plan

        fake_anthropic([(lambda s, p: True, self._plan_json("true"))])
        assert lesson_plan.generate_lesson_plan("נושא", [], api_key="k")["presentation"] is True

    def test_missing_flag_defaults_to_no_slides(self, fake_anthropic):
        import lesson_plan

        raw = self._plan_json("true").replace(',"presentation":true', "")
        fake_anthropic([(lambda s, p: True, raw)])
        assert lesson_plan.generate_lesson_plan("נושא", [], api_key="k")["presentation"] is False

    def test_a_stringly_typed_flag_does_not_count(self, fake_anthropic):
        import lesson_plan

        fake_anthropic([(lambda s, p: True, self._plan_json('"true"'))])
        assert lesson_plan.generate_lesson_plan("נושא", [], api_key="k")["presentation"] is False
