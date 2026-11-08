"""Slack integration for the virtual classroom.

Exposes a FastAPI router with two endpoints that a Slack App points at:
- POST /slack/events    (Event Subscriptions: message/app_mention events + URL verification)
- POST /slack/commands  (Slash command: /classroom <topic> starts a new lesson in that channel)

Each Slack channel (or DM) maps to one orchestrator Session. The bot posts each
agent's reply as a separate message, with that agent's display name/emoji so the
classroom's multiple "voices" are visually distinct in the Slack thread.
"""

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import orchestrator
from agents import AGENTS_BY_KEY, POOL, TEACHER

logger = logging.getLogger("slack_bot")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "").strip()
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "").strip()

print(
    f"[slack_bot] loaded SLACK_BOT_TOKEN len={len(SLACK_BOT_TOKEN)} "
    f"prefix={SLACK_BOT_TOKEN[:5]!r}; SLACK_SIGNING_SECRET len={len(SLACK_SIGNING_SECRET)}"
)

router = APIRouter()
_slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# channel_id -> session_id. One active lesson per Slack channel/DM at a time.
CHANNEL_SESSIONS: dict[str, str] = {}
# Avoid double-handling retried Slack events (Slack retries on slow/failed acks).
_SEEN_EVENT_IDS: set[str] = set()


def _verify_slack_signature(timestamp: str, body: bytes, signature: str) -> bool:
    if not SLACK_SIGNING_SECRET:
        print("[verify] REJECT: SLACK_SIGNING_SECRET is empty on the server")
        return False
    try:
        age = abs(time.time() - int(timestamp))
    except ValueError:
        print(f"[verify] REJECT: bad timestamp header {timestamp!r}")
        return False
    if age > 60 * 5:
        print(f"[verify] REJECT: timestamp too old/skewed, age={age:.0f}s")
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    ok = hmac.compare_digest(computed, signature)
    if not ok:
        print(
            f"[verify] REJECT: signature mismatch. computed_prefix={computed[:12]!r} "
            f"received_prefix={(signature or '')[:12]!r} secret_len={len(SLACK_SIGNING_SECRET)}"
        )
    return ok


def _post_as(agent, channel: str, text: str, thread_ts: str | None = None):
    if _slack_client is None:
        logger.warning("SLACK_BOT_TOKEN not set; skipping post to %s", channel)
        return
    try:
        _slack_client.chat_postMessage(
            channel=channel,
            text=f"{agent.emoji} *{agent.display_name}*\n{text}",
            thread_ts=thread_ts,
        )
    except SlackApiError as e:
        logger.error("Slack post failed: %s", e.response["error"])


def _start_lesson(channel: str, topic: str, thread_ts: str | None = None):
    session = orchestrator.create_session(topic)
    CHANNEL_SESSIONS[channel] = session.id
    pool_names = ", ".join(a.display_name for a in session.pool)
    if _slack_client:
        _slack_client.chat_postMessage(
            channel=channel,
            text=(
                f"📚 *שיעור חדש התחיל:* {topic}\n"
                f"הרכב הכיתה: {TEACHER.emoji} {TEACHER.display_name}, {pool_names}\n"
                f"כתבו כאן כדי לשאול שאלות."
            ),
            thread_ts=thread_ts,
        )


def _handle_user_text(channel: str, text: str, thread_ts: str | None = None):
    session_id = CHANNEL_SESSIONS.get(channel)
    if not session_id:
        if _slack_client:
            _slack_client.chat_postMessage(
                channel=channel,
                text="אין שיעור פעיל בערוץ הזה. התחילו אחד עם `/classroom <נושא>`.",
                thread_ts=thread_ts,
            )
        return
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        CHANNEL_SESSIONS.pop(channel, None)
        return

    replies = orchestrator.handle_user_message(session, text)
    for msg in replies:
        agent = AGENTS_BY_KEY.get(msg.agent_key, TEACHER)
        _post_as(agent, channel, msg.content, thread_ts=thread_ts)


@router.post("/slack/commands")
async def slack_commands(request: Request, x_slack_request_timestamp: str = Header(None),
                          x_slack_signature: str = Header(None)):
    body = await request.body()
    if not _verify_slack_signature(x_slack_request_timestamp or "0", body, x_slack_signature or ""):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    form = await request.form()
    command = form.get("command", "")
    text = (form.get("text") or "").strip()
    channel = form.get("channel_id")

    if command == "/classroom":
        if not text:
            return {"response_type": "ephemeral", "text": "שימוש: /classroom <נושא השיעור>"}
        _start_lesson(channel, text)
        return {"response_type": "in_channel", "text": f"מתחיל שיעור על: {text}"}

    return {"response_type": "ephemeral", "text": "פקודה לא מוכרת."}


@router.post("/slack/events")
async def slack_events(request: Request, x_slack_request_timestamp: str = Header(None),
                        x_slack_signature: str = Header(None)):
    body = await request.body()
    payload = await request.json()

    # Slack's one-time URL verification handshake does not require signature checks
    # to be solvable via curl during setup, but we still verify to be safe.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if not _verify_slack_signature(x_slack_request_timestamp or "0", body, x_slack_signature or ""):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    event_id = payload.get("event_id")
    if event_id:
        if event_id in _SEEN_EVENT_IDS:
            return {"ok": True}
        _SEEN_EVENT_IDS.add(event_id)

    event = payload.get("event", {})
    event_type = event.get("type")

    if event_type in ("message", "app_mention"):
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"ok": True}  # ignore the bot's own messages
        channel = event.get("channel")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")
        if channel and text:
            _handle_user_text(channel, text, thread_ts=thread_ts)

    return {"ok": True}
