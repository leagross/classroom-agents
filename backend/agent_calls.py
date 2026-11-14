"""Low-level calls into the Anthropic API, shared by every part of the
classroom (chat turns, the teacher's verification loop, quizzes, lesson
plans). Nothing in this file knows about Session, the DB, or any specific
agent's role — it only knows how to talk to the model.
"""

import os

import anthropic

MODEL = os.environ.get("CLASSROOM_MODEL", "claude-sonnet-5-5")
AGENT_MAX_TOKENS = 1024

# Seconds between words when "replaying" text that was already generated and
# validated in full before any of it was safe to show (the teacher's
# verified answer, a lesson plan's pre-written checkpoint question).
TEACHER_REPLAY_DELAY = 0.02

LATEX_INSTRUCTION = (
    "אם בתשובה שלך יש נוסחה מתמטית, כתוב אותה בפורמט LaTeX: נוסחה בתוך השורה בין $ $ "
    "(למשל $x^2+1$), ונוסחה בשורה נפרדת בין $$ $$. אל תשתמש בפורמט הזה לשום דבר חוץ מנוסחאות. "
)


class MissingApiKeyError(Exception):
    pass


def get_client(api_key: str | None) -> anthropic.Anthropic:
    """Every caller must bring its own Anthropic API key — there is no shared
    server-side key for the web chat. (The Slack integration is the one
    exception: it has no browser to hold a per-user key, so it supplies its
    own dedicated SLACK_ANTHROPIC_API_KEY explicitly — see slack_bot.py.)
    The key is used to build a one-off client for this call only; it is never
    logged, cached, or persisted to the DB."""
    if not api_key:
        raise MissingApiKeyError("No Anthropic API key was provided for this request.")
    return anthropic.Anthropic(api_key=api_key)


def build_user_content(text: str, image: dict | None):
    """Plain string when there's no image (unchanged, minimal request shape);
    a content-block list with an image block when there is one — only the
    teacher ever receives `image`, so it can actually look at what the
    student uploaded instead of just reading a '[image attached]' note."""
    if not image:
        return text
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": image["media_type"], "data": image["data"]},
        },
        {"type": "text", "text": text},
    ]


def call_agent(
    agent, transcript: str, extra_instruction: str = "", api_key: str | None = None, image: dict | None = None
) -> str:
    user_text = (
        f"{transcript}\n\n"
        f"הגב כעת כ-{agent.display_name}, בהתאם לכללים שלך. "
        f"{extra_instruction}"
        f"{LATEX_INSTRUCTION}"
        "כתוב רק את התגובה שלך, בלי לציין את שמך."
    )
    response = get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=agent.system_prompt,
        messages=[{"role": "user", "content": build_user_content(user_text, image)}],
    )
    block_types = [b.type for b in response.content]
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    print(
        f"[call_agent] agent={agent.key} stop_reason={response.stop_reason} "
        f"blocks={block_types} usage={response.usage} text_len={len(text)}"
    )
    if not text:
        # Defensive fallback: an empty reply (e.g. truncated generation) must never
        # be fed back into the transcript, since that poisons later turns.
        text = "(לא הצלחתי לנסח תגובה הפעם, נסה לנסח את השאלה מעט אחרת.)"
    return text


def call_agent_stream(agent, transcript: str, api_key: str | None = None):
    """Like call_agent, but yields text deltas as they arrive from the model
    instead of waiting for the full response. Used for agents that don't need
    verification (everyone except the teacher), where there's no reason to
    hold text back from the user."""
    user_content = (
        f"{transcript}\n\n"
        f"הגב כעת כ-{agent.display_name}, בהתאם לכללים שלך. "
        f"{LATEX_INSTRUCTION}"
        "כתוב רק את התגובה שלך, בלי לציין את שמך."
    )
    with get_client(api_key).messages.stream(
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=agent.system_prompt,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def word_chunks(text: str):
    """Split already-generated text into word-sized pieces so it can be
    'replayed' to the client incrementally — used for text that must be
    fully generated (and possibly verified) before any of it is shown."""
    parts = text.split(" ")
    for i, part in enumerate(parts):
        yield part + (" " if i < len(parts) - 1 else "")
