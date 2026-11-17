"""Stage 1: intake.

The profile is a gate (no plan or syllabus without one), the diagnostic is
graded by a rule rather than a model, and the student's level changes what
the teacher treats as already known.
"""

import json

import pytest
from fastapi.testclient import TestClient

import diagnostic
import session_state
from domain.learner import InvalidProfileError, LearnerProfile
from domain.phases.intake import IntakeFlow, IntakeState
from domain.teacher_actions import AnswerQuestionAction, ExplainAction, ReteachAction

KEY = {"X-Anthropic-Key": "sk-test"}

GOOD_PROFILE = {
    "time_budget_minutes": 45,
    "target_depth": "practical",
    "starting_level": "intermediate",
    "goal": "להבין לעומק",
}

PLAN_JSON = json.dumps(
    {
        "goals": ["g"],
        "activities": [
            {"stage": "teaching", "title": "t", "summary": "s", "autonomous_exchanges": 1, "checkpoint_question": "q"}
        ],
        "homework": "",
        "presentation": False,
    }
)

SYLLABUS_JSON = json.dumps([{"title": "שיעור 1", "summary": "ס"}, {"title": "שיעור 2", "summary": "ס"}])


def http():
    import main

    return TestClient(main.app)


def quiz_json(correct=0):
    return json.dumps(
        [
            {"question": "ב1", "options": ["א", "ב", "ג", "ד"], "correct_index": correct, "difficulty": "basic"},
            {"question": "ב2", "options": ["א", "ב", "ג", "ד"], "correct_index": correct, "difficulty": "basic"},
            {"question": "ב3", "options": ["א", "ב", "ג", "ד"], "correct_index": correct, "difficulty": "intermediate"},
            {"question": "ב4", "options": ["א", "ב", "ג", "ד"], "correct_index": correct, "difficulty": "advanced"},
        ]
    )


class TestLearnerProfileValidation:
    def test_a_complete_profile_is_accepted(self):
        p = LearnerProfile.from_dict({**GOOD_PROFILE, "topic": "חדו\"א"})
        assert p.starting_level == "intermediate" and p.time_budget_minutes == 45

    @pytest.mark.parametrize(
        "patch",
        [
            {"topic": "  "},
            {"time_budget_minutes": None},
            {"time_budget_minutes": "45"},
            {"time_budget_minutes": True},  # bool is an int subclass: must not pass as 1 minute
            {"time_budget_minutes": 2},
            {"time_budget_minutes": 99999},
            {"target_depth": "deep"},
            {"starting_level": "guru"},
            {"level_source": "guessed"},
        ],
    )
    def test_invalid_values_are_rejected(self, patch):
        with pytest.raises(InvalidProfileError):
            LearnerProfile.from_dict({**GOOD_PROFILE, "topic": "נושא", **patch})

    def test_not_an_object_is_rejected(self):
        with pytest.raises(InvalidProfileError):
            LearnerProfile.from_dict(None)

    def test_round_trips(self):
        p = LearnerProfile.from_dict({**GOOD_PROFILE, "topic": "נושא"})
        assert LearnerProfile.from_dict(p.to_dict()) == p

    def test_the_prompt_says_whether_the_level_was_diagnosed(self):
        stated = LearnerProfile.from_dict({**GOOD_PROFILE, "topic": "נ"})
        diagnosed = LearnerProfile.from_dict({**GOOD_PROFILE, "topic": "נ", "level_source": "diagnosed"})
        assert "לפי דיווח התלמיד" in stated.describe()
        assert "בוחן אבחון" in diagnosed.describe()


class TestIntakeFlowPosition:
    """Where intake stands is read off the form's values — one definition,
    which the server enforces and the form mirrors."""

    @pytest.mark.parametrize(
        "data,expected",
        [
            ({}, IntakeState.CHOOSING_TOPIC),
            ({"topic": "x"}, IntakeState.GATHERING_CONTEXT),
            ({"topic": "x", "time_budget_minutes": 30}, IntakeState.GATHERING_CONTEXT),
            ({"topic": "x", "time_budget_minutes": 30, "target_depth": "basics"}, IntakeState.DIAGNOSING_LEVEL),
            (
                {"topic": "x", "time_budget_minutes": 30, "target_depth": "basics", "starting_level": "beginner"},
                IntakeState.READY,
            ),
        ],
    )
    def test_position_follows_what_is_filled_in(self, data, expected):
        assert IntakeFlow.from_partial(data).state is expected

    def test_a_later_answer_does_not_skip_an_earlier_missing_one(self):
        # A level with no time or depth is still stuck at the context step.
        flow = IntakeFlow.from_partial({"topic": "x", "starting_level": "expert"})
        assert flow.state is IntakeState.GATHERING_CONTEXT
        assert not flow.is_done()


class TestLevelRule:
    @pytest.mark.parametrize(
        "results,level",
        [
            ([("basic", True), ("basic", True), ("intermediate", True), ("advanced", True)], "expert"),
            ([("basic", True), ("basic", True), ("intermediate", True), ("advanced", False)], "intermediate"),
            ([("basic", True), ("basic", True), ("intermediate", False), ("advanced", False)], "intermediate"),
            ([("basic", False), ("basic", True), ("intermediate", True), ("advanced", True)], "beginner"),
            ([("basic", False), ("basic", False), ("intermediate", False), ("advanced", False)], "beginner"),
        ],
    )
    def test_rule(self, results, level):
        assert diagnostic.level_from_results(results) == level

    def test_missing_one_basic_outweighs_getting_the_hard_ones_right(self):
        """Lucky guesses on the top questions must not place someone above a
        gap in the foundations."""
        results = [("basic", False), ("basic", True), ("intermediate", True), ("advanced", True)]
        assert diagnostic.level_from_results(results) == "beginner"


class TestDiagnostic:
    def test_correct_answers_never_reach_the_client(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json())])
        d = diagnostic.generate_diagnostic("נושא")
        assert len(d["questions"]) == 4
        for q in d["questions"]:
            assert "correct_index" not in q

    def test_questions_are_ordered_easiest_first(self, fake_anthropic):
        shuffled = json.loads(quiz_json())[::-1]
        fake_anthropic([(lambda s, p: True, json.dumps(shuffled))])
        d = diagnostic.generate_diagnostic("נושא")
        assert [q["difficulty"] for q in d["questions"]] == ["basic", "basic", "intermediate", "advanced"]

    def test_grading_uses_the_servers_copy_of_the_answers(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json(correct=2))])
        d = diagnostic.generate_diagnostic("נושא")
        result = diagnostic.grade_diagnostic(d["id"], [2, 2, 2, 2])
        assert result == {"level": "expert", "correct": 4, "total": 4}

    def test_an_unanswered_question_counts_as_wrong(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json(correct=1))])
        d = diagnostic.generate_diagnostic("נושא")
        assert diagnostic.grade_diagnostic(d["id"], [None, 1, 1, 1])["level"] == "beginner"

    def test_a_diagnostic_can_only_be_graded_once(self, fake_anthropic):
        """Otherwise a student could retry the same questions until they got
        the level they wanted."""
        fake_anthropic([(lambda s, p: True, quiz_json())])
        d = diagnostic.generate_diagnostic("נושא")
        diagnostic.grade_diagnostic(d["id"], [0, 0, 0, 0])
        with pytest.raises(diagnostic.UnknownDiagnosticError):
            diagnostic.grade_diagnostic(d["id"], [1, 1, 1, 1])

    def test_wrong_number_of_answers_is_rejected(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json())])
        d = diagnostic.generate_diagnostic("נושא")
        with pytest.raises(diagnostic.InvalidAnswersError):
            diagnostic.grade_diagnostic(d["id"], [0, 0])

    def test_malformed_model_output_raises_after_retries(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, "לא JSON")])
        with pytest.raises(diagnostic.DiagnosticGenerationError):
            diagnostic.generate_diagnostic("נושא")

    def test_a_question_with_an_out_of_range_answer_is_rejected(self, fake_anthropic):
        bad = json.loads(quiz_json())
        bad[0]["correct_index"] = 9
        fake_anthropic([(lambda s, p: True, json.dumps(bad))])
        with pytest.raises(diagnostic.DiagnosticGenerationError):
            diagnostic.generate_diagnostic("נושא")


class TestIntakeIsAGate:
    def test_no_plan_without_a_profile(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        res = http().post("/api/lesson-plan", json={"topic": "נושא"}, headers=KEY)
        assert res.status_code == 422
        assert "זמן" in res.json()["detail"]
        assert client_fake.messages.calls == []  # no model call was spent

    def test_the_missing_level_is_named(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        partial = {"time_budget_minutes": 30, "target_depth": "basics"}
        res = http().post("/api/lesson-plan", json={"topic": "נושא", "profile": partial}, headers=KEY)
        assert res.status_code == 422
        assert "רמת פתיחה" in res.json()["detail"]

    def test_an_invalid_value_is_a_422_not_a_crash(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        bad = {**GOOD_PROFILE, "time_budget_minutes": 1}
        res = http().post("/api/lesson-plan", json={"topic": "נושא", "profile": bad}, headers=KEY)
        assert res.status_code == 422

    def test_a_complete_profile_builds_a_plan_that_carries_it(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        res = http().post("/api/lesson-plan", json={"topic": "נושא", "profile": GOOD_PROFILE}, headers=KEY)
        assert res.status_code == 200
        plan = res.json()["plan"]
        assert plan["learner"]["starting_level"] == "intermediate"
        assert plan["learner"]["topic"] == "נושא"
        # ...and the planner was actually told who the student is.
        sent = str(client_fake.messages.calls[-1]["messages"])
        assert "בינוני" in sent and "45 דקות" in sent

    def test_no_syllabus_without_a_profile(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, SYLLABUS_JSON)])
        res = http().post("/api/syllabus", json={"topic": "נושא"}, headers=KEY)
        assert res.status_code == 422

    def test_a_syllabus_is_built_for_and_keeps_the_profile(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, SYLLABUS_JSON)])
        c = http()
        preview = c.post("/api/syllabus", json={"topic": "נושא", "profile": GOOD_PROFILE}, headers=KEY)
        assert preview.status_code == 200
        assert preview.json()["profile"]["starting_level"] == "intermediate"
        assert "בינוני" in str(client_fake.messages.calls[-1]["messages"])

        created = c.post(
            "/api/syllabus/create",
            json={"topic": "נושא", "lessons": preview.json()["lessons"], "profile": GOOD_PROFILE},
        )
        assert created.status_code == 200
        assert created.json()["profile"]["target_depth"] == "practical"

    def test_a_lesson_planned_later_is_written_for_the_same_student(self, fake_anthropic):
        """Plans inside a syllabus are generated lazily, possibly days later.
        They must use the profile the syllabus was built for."""
        client_fake = fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        c = http()
        created = c.post(
            "/api/syllabus/create",
            json={"topic": "נושא", "lessons": [{"title": "שיעור 1", "summary": "ס"}], "profile": GOOD_PROFILE},
        ).json()

        res = c.post(f"/api/syllabus/{created['id']}/lesson/0/plan", headers=KEY)

        assert res.status_code == 200
        assert res.json()["plan"]["learner"]["starting_level"] == "intermediate"
        assert "בינוני" in str(client_fake.messages.calls[-1]["messages"])

    def test_a_syllabus_from_before_intake_existed_still_works(self, fake_anthropic):
        import syllabus as syllabus_module

        fake_anthropic([(lambda s, p: True, PLAN_JSON)])
        old = syllabus_module.SYLLABI.setdefault(
            "old", {"id": "old", "topic": "נושא", "lessons": [{"title": "ש", "summary": "", "status": "not_started"}],
                    "user_email": None}
        )
        res = http().post(f"/api/syllabus/{old['id']}/lesson/0/plan", headers=KEY)
        assert res.status_code == 200
        assert "learner" not in res.json()["plan"]


class TestDiagnosticRoutes:
    def test_start_then_grade(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json(correct=3))])
        c = http()
        started = c.post("/api/intake/diagnostic", json={"topic": "נושא"}, headers=KEY).json()
        assert "correct_index" not in json.dumps(started)
        graded = c.post(f"/api/intake/diagnostic/{started['id']}/grade", json={"answers": [3, 3, 3, 3]})
        assert graded.json()["level"] == "expert"

    def test_grading_twice_is_a_404(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, quiz_json())])
        c = http()
        started = c.post("/api/intake/diagnostic", json={"topic": "נושא"}, headers=KEY).json()
        c.post(f"/api/intake/diagnostic/{started['id']}/grade", json={"answers": [0, 0, 0, 0]})
        again = c.post(f"/api/intake/diagnostic/{started['id']}/grade", json={"answers": [0, 0, 0, 0]})
        assert again.status_code == 404

    def test_a_blank_topic_is_rejected_before_any_model_call(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, quiz_json())])
        res = http().post("/api/intake/diagnostic", json={"topic": "   "}, headers=KEY)
        assert res.status_code == 422
        assert client_fake.messages.calls == []


class TestLevelChangesWhatTheTeacherAssumes:
    def _session(self, level):
        plan = {
            "goals": ["g"],
            "activities": [
                {"stage": "teaching", "title": "נגזרות", "summary": "s", "autonomous_exchanges": 0,
                 "checkpoint_question": "q"}
            ],
            "homework": "",
            "learner": {**GOOD_PROFILE, "topic": "חדו\"א", "starting_level": level},
        }
        return session_state.create_session("חדו\"א", pool_keys=["dani", "deep_diver"], plan=plan)

    def test_a_beginner_is_assumed_to_know_nothing(self):
        s = self._session("beginner")
        prompt = ExplainAction().build_prompt(s, s.lesson)
        assert "לא מכיר את הנושא בכלל" in prompt
        assert "אל תניח שום ידע קודם" in prompt

    def test_an_intermediate_student_gets_basics_as_a_recap_and_new_things_in_full(self):
        s = self._session("intermediate")
        prompt = ExplainAction().build_prompt(s, s.lesson)
        assert "מכיר את יסודות התחום" in prompt
        assert "די בתזכורת קצרה" in prompt
        assert "לא מכיר את הנושא בכלל" not in prompt
        # ...but anything new to them is still explained fully, before use.
        assert "קודם מסבירים, ורק אחר כך מציגים" in prompt
        assert "כאילו אינו מכיר" in prompt

    def test_an_expert_is_not_walked_through_the_basics(self):
        s = self._session("expert")
        prompt = ExplainAction().build_prompt(s, s.lesson)
        assert "אל תסביר יסודות" in prompt
        assert "אל תניח שום ידע קודם" not in prompt

    def test_the_requested_depth_reaches_the_teacher(self):
        s = self._session("beginner")
        assert "העומק המבוקש: שימושי" in ExplainAction().build_prompt(s, s.lesson)

    def test_every_teaching_action_reads_the_level_not_just_the_first(self):
        s = self._session("expert")
        for action in (ExplainAction(), ReteachAction(), AnswerQuestionAction()):
            assert "אל תסביר יסודות" in action.build_prompt(s, s.lesson), type(action).__name__

    def test_no_profile_means_assume_nothing(self):
        s = session_state.create_session("נושא", pool_keys=["dani", "deep_diver"], plan=None)
        assert "אל תניח שום ידע קודם" in AnswerQuestionAction().build_prompt(s, s.lesson)

    def test_a_corrupt_stored_profile_does_not_stop_the_lesson(self):
        s = self._session("beginner")
        s.lesson.plan["learner"] = {"starting_level": "wizard"}
        prompt = ExplainAction().build_prompt(s, s.lesson)  # must not raise
        assert "אל תניח שום ידע קודם" in prompt
