"""A fake Anthropic client, so the pipeline can be driven end to end without
network access or an API key.

The old code had no tests at all, and its stated verification plan was
"curl both routes and compare" — which can't work against a live model,
since no two runs produce the same text. Everything here is deterministic.
"""

import sys
import types

import pytest

# Import every module that holds a reference to get_client NOW, at collection
# time, before any test has patched anything. A module first imported inside
# a test body would otherwise do `from agent_calls import get_client` while
# the fake is installed and keep that test's stub bound for the rest of the
# session, so later tests would silently talk to an earlier test's fake.
import agent_calls  # noqa: F401,E402
import diagnostic  # noqa: F401,E402
import flashcards  # noqa: F401,E402
import lesson_plan  # noqa: F401,E402
import main  # noqa: F401,E402
import quiz  # noqa: F401,E402
import slides  # noqa: F401,E402
import syllabus  # noqa: F401,E402
import domain.teacher_actions  # noqa: F401,E402


class FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, text):
        self.content = [FakeTextBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = None


class FakeStream:
    """Context manager matching anthropic's messages.stream() surface."""

    def __init__(self, text):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        yield self._text


class FakeMessages:
    def __init__(self, script):
        self._script = script
        self.calls = []

    def _reply_for(self, system, messages):
        self.calls.append({"system": system, "messages": messages})
        prompt = str(messages)
        for matcher, reply in self._script:
            if matcher(system or "", prompt):
                return reply(prompt) if callable(reply) else reply
        return "תגובה כללית."

    def create(self, model=None, max_tokens=None, system=None, messages=None, **kwargs):
        return FakeResponse(self._reply_for(system, messages))

    def stream(self, model=None, max_tokens=None, system=None, messages=None, **kwargs):
        return FakeStream(self._reply_for(system, messages))


class FakeClient:
    def __init__(self, script):
        self.messages = FakeMessages(script)


def is_verifier(system: str, prompt: str) -> bool:
    return "אימות" in system or "שכבת אימות" in system


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patches get_client everywhere it's imported. Pass a script: a list of
    (matcher, reply) pairs, where matcher(system, prompt) -> bool."""

    state = {"client": None}

    def install(script):
        client = FakeClient(script)
        state["client"] = client
        # Modules do `from agent_calls import get_client`, so each holds its
        # own reference. Patch every module that has one rather than listing
        # them by name — a list silently misses any module added later, and
        # the test then fails on a missing API key instead of the behaviour
        # it meant to check.
        import agent_calls

        original = agent_calls.get_client
        stub = lambda api_key=None: client  # noqa: E731
        stub._is_fake_client = True
        for module in list(sys.modules.values()):
            if module is None:
                continue
            current = getattr(module, "get_client", None)
            # Also re-point a stub left over from an earlier test, which
            # would otherwise keep answering from that test's script.
            if current is original or getattr(current, "_is_fake_client", False):
                monkeypatch.setattr(module, "get_client", stub, raising=False)
        return client

    install.state = state
    return install


@pytest.fixture(autouse=True)
def no_db(monkeypatch):
    """Keep every test in-memory: db.py no-ops without DATABASE_URL anyway,
    but this makes it explicit and independent of the environment."""
    import db

    monkeypatch.setattr(db, "_engine", None, raising=False)


@pytest.fixture(autouse=True)
def clean_sessions():
    import session_state

    session_state.SESSIONS.clear()
    yield
    session_state.SESSIONS.clear()
