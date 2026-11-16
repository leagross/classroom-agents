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
