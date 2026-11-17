"""Slides are a companion to the lesson, never a blocker — these pin that
down, including that a broken design provider still yields usable slides.
"""

import pytest

import slides as slides_module
from tests.conftest import is_verifier

ACTIVITY = {"title": "נגזרות", "summary": "הגדרת הנגזרת"}

GOOD_JSON = '[{"title": "מה זה נגזרת", "bullets": ["קצב שינוי", "דוגמה"]}]'


class TestGeneration:
    def test_parses_a_well_formed_deck(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        deck = slides_module.generate_activity_slides("חדו\"א", ACTIVITY)
        assert deck == [{"title": "מה זה נגזרת", "bullets": ["קצב שינוי", "דוגמה"]}]

    def test_missing_bullets_become_an_empty_list_rather_than_failing(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, '[{"title": "כותרת בלבד"}]')])
        deck = slides_module.generate_activity_slides("נושא", ACTIVITY)
        assert deck[0]["bullets"] == []

    def test_blank_bullets_are_dropped(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, '[{"title": "ת", "bullets": ["שורה", "  ", ""]}]')])
        deck = slides_module.generate_activity_slides("נושא", ACTIVITY)
        assert deck[0]["bullets"] == ["שורה"]

    def test_unparseable_output_raises_after_retries(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, "לא JSON בכלל")])
        with pytest.raises(slides_module.SlideGenerationError):
            slides_module.generate_activity_slides("נושא", ACTIVITY)

    def test_prompt_carries_the_activity_being_taught(self, fake_anthropic):
        client = fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        slides_module.generate_activity_slides("חדו\"א", ACTIVITY)
        sent = str(client.messages.calls[-1]["messages"])
        assert "נגזרות" in sent and "הגדרת הנגזרת" in sent


class TestProviderSeam:
    def test_default_provider_passes_the_text_slides_through(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        assert slides_module.build_slides("נושא", ACTIVITY)[0]["title"] == "מה זה נגזרת"

    def test_a_provider_may_add_a_rendered_image(self, fake_anthropic, monkeypatch):
        fake_anthropic([(lambda s, p: True, GOOD_JSON)])

        class Designed(slides_module.SlideProvider):
            name = "test-designer"

            def render(self, deck, topic):
                return [{**s, "image_url": "https://example.test/1.png"} for s in deck]

        monkeypatch.setattr(slides_module, "_provider", Designed())
        assert slides_module.build_slides("נושא", ACTIVITY)[0]["image_url"].endswith("1.png")

    def test_a_failing_provider_falls_back_to_text_slides(self, fake_anthropic, monkeypatch):
        """A design-tool outage must cost the lesson its styling, not its slides."""
        fake_anthropic([(lambda s, p: True, GOOD_JSON)])

        class Broken(slides_module.SlideProvider):
            name = "broken"

            def render(self, deck, topic):
                raise RuntimeError("design service down")

        monkeypatch.setattr(slides_module, "_provider", Broken())
        deck = slides_module.build_slides("נושא", ACTIVITY)
        assert deck[0]["title"] == "מה זה נגזרת"
        assert "image_url" not in deck[0]


class TestWhetherALessonHasSlides:
    """The lesson's type decides whether anything is projected; the teacher
    writes on the board either way."""

    def _client(self):
        from fastapi.testclient import TestClient

        import main

        return TestClient(main.app)

    def _session(self, presentation):
        import session_state

        plan = {
            "goals": ["g"],
            "activities": [{"stage": "teaching", "title": "נגזרות", "summary": "s",
                            "autonomous_exchanges": 0, "checkpoint_question": "q"}],
            "homework": "",
            "presentation": presentation,
        }
        return session_state.create_session("נושא", pool_keys=["dani", "deep_diver"], plan=plan)

    def test_a_lesson_without_a_presentation_cannot_spend_a_deck(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        session = self._session(presentation=False)
        res = self._client().get(
            f"/api/session/{session.id}/slides/0", headers={"X-Anthropic-Key": "sk-test"}
        )
        assert res.status_code == 404
        assert client_fake.messages.calls == []  # no model call was made

    def test_a_lesson_with_a_presentation_gets_its_deck_once(self, fake_anthropic):
        client_fake = fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        session = self._session(presentation=True)
        http = self._client()
        headers = {"X-Anthropic-Key": "sk-test"}

        first = http.get(f"/api/session/{session.id}/slides/0", headers=headers)
        second = http.get(f"/api/session/{session.id}/slides/0", headers=headers)

        assert first.status_code == 200 and first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert len(client_fake.messages.calls) == 1  # the second request was served from cache

    def test_an_out_of_range_activity_is_a_404(self, fake_anthropic):
        fake_anthropic([(lambda s, p: True, GOOD_JSON)])
        session = self._session(presentation=True)
        res = self._client().get(
            f"/api/session/{session.id}/slides/9", headers={"X-Anthropic-Key": "sk-test"}
        )
        assert res.status_code == 404
